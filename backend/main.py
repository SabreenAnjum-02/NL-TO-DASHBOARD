# DataSense AI Backend - Consolidated Entry Point
"""
FastAPI entry point that combines all routers, services, and the agent orchestrator.

v2 changes:
- Disk-based DuckDB (survives within-process reconnects)
- Uploaded files saved to datasense_storage/uploads/ for auto-reingest
- Rich dataset profile: types, null counts, sample values, distinct counts,
  min/max for numeric and date columns, cardinality hints for categorical columns
- session_expired error with specific code so frontend can show useful message
- execute_query() for the text-answer agent (SELECT only, parameterised table name)
"""

import os
import uuid
import tempfile
import json
import shutil
from typing import Optional

import duckdb
import pdfplumber
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="DataSense AI API",
    description="Natural Language to Dashboard Generation - Agentic AI Backend",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Data Service (Singleton)
# ─────────────────────────────────────────────────────────────────────────────
STORAGE_DIR = "datasense_storage"
UPLOADS_DIR = os.path.join(STORAGE_DIR, "uploads")
DB_PATH = os.path.join(STORAGE_DIR, "db.duckdb")


class DataService:
    """Manages data ingestion, storage, and profiling.

    Persistence strategy (no external DB required):
    - Uses a disk-based DuckDB file so tables survive within-process reconnects.
    - Saves the uploaded file to UPLOADS_DIR so data can be re-ingested after a
      DuckDB table loss (e.g. a DuckDB connection reset within the same OS process).
    - On a full Render restart the OS filesystem is wiped, so the re-ingest
      fallback won't fire; instead we raise session_expired so the frontend can
      prompt the user to re-upload with a clear, friendly message.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        # Disk-based DuckDB: survives within-process reconnects.
        self.db = duckdb.connect(DB_PATH)
        self.datasets: dict = {}
        self._initialized = True

    # ── Ingest ────────────────────────────────────────────────────────────────

    async def ingest_file(self, file: UploadFile) -> dict:
        """Ingest CSV, Excel, JSON, Parquet or PDF into DuckDB.

        The raw file is saved permanently to UPLOADS_DIR so that
        _reingest() can reconstruct the DuckDB table if it is ever lost.
        """
        dataset_id = str(uuid.uuid4())[:8]
        file_ext = "." + file.filename.rsplit(".", 1)[-1].lower()

        # Write upload to a temp location first
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        with open(temp_path, "wb") as fh:
            content = await file.read()
            fh.write(content)

        table_name = f"dataset_{dataset_id}"
        safe_path = temp_path.replace("\\", "/")

        try:
            table_names = self._load_into_duckdb(table_name, safe_path, file_ext)

            total_row_count = 0
            for t_name in table_names:
                total_row_count += self.db.execute(f'SELECT COUNT(*) FROM "{t_name}"').fetchone()[0]
                
            # Phase 3 profiling: Pass all tables for hierarchical profiling
            profile = self._build_rich_profile(table_names, total_row_count)

            # Persist the file so we can re-ingest later if needed
            saved_path = os.path.join(UPLOADS_DIR, f"{dataset_id}{file_ext}")
            shutil.copy2(temp_path, saved_path)

            self.datasets[dataset_id] = {
                "id": dataset_id,
                "filename": file.filename,
                "table_name": table_names[0], # Backwards compatibility for UI
                "table_names": table_names,
                "profile": profile,
                "file_path": saved_path,
                "file_ext": file_ext,
            }
            return {
                "dataset_id": dataset_id,
                "filename": file.filename,
                "profile": profile,
                "status": "success",
            }
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _load_into_duckdb(self, table_name: str, safe_path: str, file_ext: str) -> list[str]:
        """Parse a file and load it into DuckDB. Returns a list of created table names."""
        if file_ext == ".csv":
            self.db.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{safe_path}')"
            )
            return [table_name]

        elif file_ext in (".xlsx", ".xls"):
            import pandas as pd
            import re

            # Read all sheets without headers first
            dfs_raw = pd.read_excel(safe_path, sheet_name=None, header=None)
            table_names = []
            
            for sheet, df in dfs_raw.items():
                
                # Auto-detect header row (row with the most non-null columns in the first 20 rows)
                header_idx = 0
                max_non_nulls = 0
                for i in range(min(20, len(df))):
                    non_nulls = df.iloc[i].notna().sum()
                    if non_nulls > max_non_nulls:
                        max_non_nulls = non_nulls
                        header_idx = i
                
                if max_non_nulls > 0:
                    df.columns = df.iloc[header_idx]
                    df = df.iloc[header_idx+1:].reset_index(drop=True)

                df = df.dropna(how="all").dropna(axis=1, how="all")
                if len(df) == 0:
                    continue
                
                # Clean column names
                df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
                # Ensure unique column names to prevent DuckDB errors
                cols = pd.Series(df.columns)
                for dup in cols[cols.duplicated()].unique():
                    cols[cols[cols == dup].index.values.tolist()] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
                df.columns = cols

                # Smart type casting and safety fallback for this specific sheet
                for col in df.columns:
                    if pd.api.types.is_object_dtype(df[col]):
                        numeric = pd.to_numeric(df[col], errors="coerce")
                        orig_non_null = df[col].notna().sum()
                        if orig_non_null > 0 and numeric.notna().sum() / orig_non_null > 0.5:
                            df[col] = numeric
                        else:
                            # Force completely to string to prevent duckdb mixed-type crash
                            df[col] = df[col].astype(str).replace(["nan", "None", "<NA>"], None)
                
                clean_sheet_name = re.sub(r'[^a-zA-Z0-9_]', '_', sheet)
                sheet_table_name = f"{table_name}_{clean_sheet_name}"
                
                self.db.execute(f'CREATE TABLE "{sheet_table_name}" AS SELECT * FROM df')
                table_names.append(sheet_table_name)

            if not table_names:
                raise Exception("No valid data tables found in Excel")
            return table_names

        elif file_ext == ".json":
            self.db.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_json_auto('{safe_path}')"
            )
            return [table_name]

        elif file_ext == ".parquet":
            self.db.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_parquet('{safe_path}')"
            )
            return [table_name]

        elif file_ext == ".pdf":
            raise Exception("PDF parsing is currently experimental and limited. Please upload a CSV or Excel file for reliable structured data extraction.")

        else:
            raise Exception(f"Unsupported file type: {file_ext}")

    # ── Rich profile ──────────────────────────────────────────────────────────

    def _build_rich_profile(self, table_names: list[str], total_row_count: int) -> dict:
        """Build a rich dataset profile with multi-table support used by LLM agents."""
        profile = {
            "row_count": total_row_count, 
            "column_count": 0,
            "columns": [],
            "tables": {},
            "relationships": []
        }
        
        all_columns = []
        col_map = []
        
        for t_name in table_names:
            table_info = {
                "purpose": "unknown",
                "grain": "unknown",
                "row_count": 0,
                "columns": [],
                "primary_key_candidates": []
            }
            
            t_count = self.db.execute(f'SELECT COUNT(*) FROM "{t_name}"').fetchone()[0]
            table_info["row_count"] = t_count
            
            cols_raw = self.db.execute(f'DESCRIBE "{t_name}"').fetchall()
            
            numeric_cols = 0
            date_cols = 0
            max_distinct = 0
            
            for col_name, col_type, *_ in cols_raw:
                if col_name == "Sheet_Name": continue
                    
                col_info = {
                    "name": col_name,
                    "type": col_type,
                    "null_count": 0,
                    "samples": [],
                }
                
                try:
                    null_count = self.db.execute(f'SELECT COUNT(*) FROM "{t_name}" WHERE "{col_name}" IS NULL').fetchone()[0]
                    col_info["null_count"] = null_count
                    
                    raw_samples = self.db.execute(f'SELECT DISTINCT "{col_name}" FROM "{t_name}" WHERE "{col_name}" IS NOT NULL LIMIT 3').fetchall()
                    col_info["samples"] = [str(r[0]) for r in raw_samples]
                    
                    type_up = col_type.upper()
                    
                    if any(t in type_up for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT", "HUGEINT", "REAL", "TINYINT", "SMALLINT")):
                        numeric_cols += 1
                        row = self.db.execute(f'SELECT MIN("{col_name}"), MAX("{col_name}"), APPROX_COUNT_DISTINCT("{col_name}") FROM "{t_name}"').fetchone()
                        if row:
                            col_info["min"] = row[0]
                            col_info["max"] = row[1]
                            col_info["distinct_count"] = row[2]
                            max_distinct = max(max_distinct, row[2])
                    elif any(t in type_up for t in ("DATE", "TIMESTAMP", "TIME")):
                        date_cols += 1
                        row = self.db.execute(f'SELECT MIN("{col_name}"), MAX("{col_name}") FROM "{t_name}"').fetchone()
                        if row:
                            col_info["min_date"] = str(row[0])
                            col_info["max_date"] = str(row[1])
                            dist = self.db.execute(f'SELECT APPROX_COUNT_DISTINCT("{col_name}") FROM "{t_name}"').fetchone()[0]
                            col_info["distinct_count"] = dist
                    elif any(t in type_up for t in ("VARCHAR", "TEXT", "STRING", "CHAR")):
                        dist = self.db.execute(f'SELECT APPROX_COUNT_DISTINCT("{col_name}") FROM "{t_name}"').fetchone()[0]
                        col_info["distinct_count"] = dist
                        max_distinct = max(max_distinct, dist)
                        if dist <= 10:
                            col_info["cardinality"] = "low"
                            raw_samples_ext = self.db.execute(f'SELECT DISTINCT "{col_name}" FROM "{t_name}" WHERE "{col_name}" IS NOT NULL LIMIT 10').fetchall()
                            col_info["samples"] = [str(r[0]) for r in raw_samples_ext]
                        elif dist <= 50:
                            col_info["cardinality"] = "medium"
                        else:
                            col_info["cardinality"] = "high"
                            
                    if "distinct_count" in col_info and col_info["distinct_count"] > 0:
                        if col_info["distinct_count"] == t_count and col_info["null_count"] == 0 and t_count > 1:
                            name_lower = col_name.lower()
                            if "id" in name_lower or "code" in name_lower or name_lower == "name" or name_lower == "vendor" or name_lower == "crew" or name_lower == "employee":
                                table_info["primary_key_candidates"].append(col_name)
                                
                    col_map.append({
                        "table": t_name, 
                        "col": col_name, 
                        "type": type_up, 
                        "distinct": col_info.get("distinct_count", 0),
                        "nulls": null_count
                    })
                            
                except Exception:
                    pass
                    
                table_info["columns"].append(col_info)
                all_columns.append({"table": t_name, **col_info})
                
            name_lower = t_name.lower()
            if t_count == 0:
                table_info["grain"] = "empty"
            elif t_count == 1:
                table_info["grain"] = "metadata/single record"
                table_info["purpose"] = "summary or configuration"
            else:
                is_summary = any(kw in name_lower for kw in ("summary", "total", "aggregate", "report", "monthly", "yearly", "dashboard"))
                if is_summary:
                    table_info["grain"] = "aggregated/summary"
                    table_info["purpose"] = "pre-calculated metrics"
                else:
                    if len(table_info["primary_key_candidates"]) > 0:
                        table_info["grain"] = "entity-level (one row per entity)"
                    elif max_distinct > 0 and max_distinct < (t_count * 0.2) and date_cols > 0:
                        table_info["grain"] = "time-series/event-level (transactional)"
                    else:
                        table_info["grain"] = "detail-level/transactional (inferred)"
                        
            profile["tables"][t_name] = table_info
            
        for i in range(len(col_map)):
            for j in range(i+1, len(col_map)):
                c1, c2 = col_map[i], col_map[j]
                if c1["table"] == c2["table"]: continue
                
                n1, n2 = c1["col"].lower(), c2["col"].lower()
                
                if n1 == n2 or (n1 in n2 and "id" in n1) or (n2 in n1 and "id" in n2):
                    if ("INT" in c1["type"] and "INT" in c2["type"]) or ("CHAR" in c1["type"] and "CHAR" in c2["type"]) or c1["type"] == c2["type"]:
                        if c1["distinct"] > 0 and c2["distinct"] > 0:
                            try:
                                overlap = self.db.execute(f'SELECT COUNT(*) FROM (SELECT "{c1["col"]}" FROM "{c1["table"]}" WHERE "{c1["col"]}" IS NOT NULL INTERSECT SELECT "{c2["col"]}" FROM "{c2["table"]}" WHERE "{c2["col"]}" IS NOT NULL)').fetchone()[0]
                                if overlap > 0:
                                    confidence = "likely" if overlap >= min(c1["distinct"], c2["distinct"]) * 0.5 else "possible"
                                    profile["relationships"].append({
                                        "source_table": c1["table"],
                                        "source_column": c1["col"],
                                        "target_table": c2["table"],
                                        "target_column": c2["col"],
                                        "confidence": confidence,
                                        "overlap_count": overlap
                                    })
                            except Exception:
                                pass
                                
        profile["columns"] = all_columns
        profile["column_count"] = len(all_columns)
        
        return profile


    def get_summary(self, dataset_id: str) -> dict:
        """Return dataset metadata.

        Raises 'session_expired:{id}' if the dataset is gone and cannot be
        recovered from disk (i.e. the Render container restarted).
        Silently re-ingests if the DuckDB table is missing but the file is present.
        """
        if dataset_id not in self.datasets:
            raise Exception(f"session_expired:{dataset_id}")

        table_names = self.datasets[dataset_id].get("table_names", [self.datasets[dataset_id]["table_name"]])
        
        # Verify all DuckDB tables still exist
        try:
            for t_name in table_names:
                self.db.execute(f'SELECT 1 FROM "{t_name}" LIMIT 1')
        except Exception:
            # Table gone - try to re-ingest from saved file
            file_path = self.datasets[dataset_id].get("file_path", "")
            if file_path and os.path.exists(file_path):
                self._reingest(dataset_id)
            else:
                del self.datasets[dataset_id]
                raise Exception(f"session_expired:{dataset_id}")

        return self.datasets[dataset_id]

    def _reingest(self, dataset_id: str) -> None:
        """Re-create the DuckDB table from the saved upload file."""
        info = self.datasets[dataset_id]
        safe_path = info["file_path"].replace("\\", "/")
        table_names = info.get("table_names", [info["table_name"]])
        
        # Drop the old tables if they exist
        for t_name in table_names:
            try:
                self.db.execute(f'DROP TABLE IF EXISTS "{t_name}"')
            except Exception:
                pass
                
        new_table_names = self._load_into_duckdb(f"dataset_{dataset_id}", safe_path, info.get("file_ext", ".xlsx"))
        self.datasets[dataset_id]["table_names"] = new_table_names
        self.datasets[dataset_id]["table_name"] = new_table_names[0]
        
        # Refresh profile
        total_row_count = 0
        for t_name in new_table_names:
            total_row_count += self.db.execute(f'SELECT COUNT(*) FROM "{t_name}"').fetchone()[0]
            
        self.datasets[dataset_id]["profile"] = self._build_rich_profile(new_table_names, total_row_count)

    def get_rows(self, dataset_id: str, limit: int = 5000) -> list:
        if dataset_id not in self.datasets:
            return []
            
        table_names = self.datasets[dataset_id].get("table_names", [self.datasets[dataset_id]["table_name"]])
        limit_per_table = max(1, limit // len(table_names))
        
        all_raw_rows = []
        for t_name in table_names:
            try:
                result = self.db.execute(f'SELECT * FROM "{t_name}" LIMIT {limit_per_table}').fetchall()
                columns = [desc[0] for desc in self.db.description]
                raw_rows = [{"__table__": t_name, **{col: val for col, val in zip(columns, row)}} for row in result]
                all_raw_rows.extend(raw_rows)
            except Exception:
                continue
                
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder(all_raw_rows)

    def execute_query(self, dataset_id: str, sql: str) -> list:
        """Execute a SELECT query against a dataset and return rows as dicts.

        Security: only SELECT statements are allowed.
        Phase 4: Supports explicit table names (validated against the dataset's table list)
        and supports {{table}} as a fallback to the first table.
        """
        if dataset_id not in self.datasets:
            raise Exception(f"Dataset '{dataset_id}' not found")
        if not sql.strip().upper().startswith("SELECT") and not sql.strip().upper().startswith("WITH"):
            raise ValueError("Only SELECT or WITH queries are permitted")
            
        table_names = self.datasets[dataset_id].get("table_names", [self.datasets[dataset_id]["table_name"]])
        
        # Backward compatibility for Phase 1/2 prompts
        if "{{table}}" in sql:
            safe_sql = sql.replace('\"{{table}}\"', "{{table}}").replace("\'{{table}}\'", "{{table}}")
            safe_sql = safe_sql.replace("{{table}}", f'"{table_names[0]}"')
        else:
            safe_sql = sql
            
        # Security: ensure no other tables are accessed (naive check for dataset prefixes)
        # DuckDB will natively throw a Catalog Error if a table doesn't exist.
        # But we must ensure they don't query a table from dataset_OTHER.
        # Simple string validation: every table starting with "dataset_" must be in our table_names list.
        import re
        referenced_datasets = re.findall(r'"?(dataset_[a-zA-Z0-9]+(?:_[a-zA-Z0-9_]+)*)"?', safe_sql)
        for ref in referenced_datasets:
            if ref not in table_names and ref != f"dataset_{dataset_id}":
                raise ValueError(f"Security violation: Query attempts to access unauthorized table '{ref}'.")
                
        result = self.db.execute(safe_sql).fetchall()
        cols = [d[0] for d in self.db.description]
        return [{c: v for c, v in zip(cols, row)} for row in result]

    def list_datasets(self) -> dict:
        return {
            "datasets": [
                {
                    "id": ds["id"],
                    "filename": ds.get("filename"),
                    "rows": ds["profile"]["row_count"],
                    "columns": ds["profile"]["column_count"],
                }
                for ds in self.datasets.values()
            ]
        }


# Singleton instance
data_service = DataService()

# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"name": "DataSense AI API", "version": "2.0.0", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health_check():
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    return {"status": "healthy", "llm_configured": bool(openrouter_key)}


@app.post("/api/data/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    allowed = [".csv", ".xlsx", ".xls", ".json", ".parquet", ".pdf"]
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    try:
        result = await data_service.ingest_file(file)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/data/connect-sql")
async def connect_sql(payload: dict):
    return JSONResponse(content={
        "status": "stub",
        "message": "SQL connection is not yet implemented.",
    })


@app.get("/api/data/datasets")
async def list_datasets():
    return JSONResponse(content=data_service.list_datasets())


@app.get("/api/data/summary/{dataset_id}")
async def get_summary(dataset_id: str):
    try:
        return JSONResponse(content=data_service.get_summary(dataset_id))
    except Exception as e:
        if "session_expired" in str(e):
            raise HTTPException(status_code=410, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/data/rows/{dataset_id}")
async def get_rows(dataset_id: str, limit: int = Query(default=5000, le=10000)):
    try:
        rows = data_service.get_rows(dataset_id, limit)
        return JSONResponse(content={"rows": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse(content={"rows": [], "count": 0, "error": str(e)}, status_code=200)


from app.routers import query_router
app.include_router(query_router.router, prefix="/api/query", tags=["Query"])
