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
            self._load_into_duckdb(table_name, safe_path, file_ext)

            row_count = self.db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            profile = self._build_rich_profile(table_name, row_count)

            # Persist the file so we can re-ingest later if needed
            saved_path = os.path.join(UPLOADS_DIR, f"{dataset_id}{file_ext}")
            shutil.copy2(temp_path, saved_path)

            self.datasets[dataset_id] = {
                "id": dataset_id,
                "filename": file.filename,
                "table_name": table_name,
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

    def _load_into_duckdb(self, table_name: str, safe_path: str, file_ext: str) -> None:
        """Parse a file and load it into DuckDB. Raises on unsupported type."""
        if file_ext == ".csv":
            self.db.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{safe_path}')"
            )

        elif file_ext in (".xlsx", ".xls"):
            import pandas as pd

            # Read all sheets without headers first
            dfs_raw = pd.read_excel(safe_path, sheet_name=None, header=None)
            all_dfs = []
            for sheet, df in dfs_raw.items():
                lower = sheet.lower()
                # Skip non-data sheets
                if any(kw in lower for kw in ("how to", "read me", "welcome")):
                    continue
                
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

                df["Sheet_Name"] = sheet
                all_dfs.append(df)

            if not all_dfs:
                df = pd.DataFrame({"Error": ["No valid data tables found in Excel"]})
            else:
                df = pd.concat(all_dfs, ignore_index=True)
                # Smart type casting and safety fallback
                for col in df.columns:
                    if col == "Sheet_Name":
                        continue
                        
                    if pd.api.types.is_object_dtype(df[col]):
                        numeric = pd.to_numeric(df[col], errors="coerce")
                        orig_non_null = df[col].notna().sum()
                        if orig_non_null > 0 and numeric.notna().sum() / orig_non_null > 0.5:
                            df[col] = numeric
                        else:
                            # Force completely to string to prevent duckdb mixed-type crash
                            df[col] = df[col].astype(str).replace(["nan", "None", "<NA>"], None)

            self.db.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')

        elif file_ext == ".json":
            self.db.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_json_auto('{safe_path}')"
            )

        elif file_ext == ".parquet":
            self.db.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_parquet('{safe_path}')"
            )

        elif file_ext == ".pdf":
            with pdfplumber.open(safe_path) as pdf:
                table = pdf.pages[0].extract_table()
                if not table:
                    raise Exception("No table found in PDF")
            import csv, io
            buf = io.StringIO()
            csv.writer(buf).writerows(table)
            buf.seek(0)
            tmp_csv = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            tmp_csv.write(buf.getvalue().encode())
            tmp_csv.close()
            csv_path = tmp_csv.name.replace("\\", "/")
            try:
                self.db.execute(
                    f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{csv_path}')"
                )
            finally:
                os.unlink(csv_path)

        else:
            raise Exception(f"Unsupported file type: {file_ext}")

    # ── Rich profile ──────────────────────────────────────────────────────────

    def _build_rich_profile(self, table_name: str, row_count: int) -> dict:
        """Build a rich dataset profile used by the LLM agents.

        Includes: column name, DuckDB type, null count, 3 sample values,
        approximate distinct count, and (for numeric) min/max,
        (for dates) min/max date, (for low-cardinality text) cardinality hint.

        Kept efficient:
        - Uses DuckDB's APPROX_COUNT_DISTINCT for distinct counts (O(1) memory).
        - Skips per-column stat queries for empty columns gracefully.
        - Limits sample fetching to 3 DISTINCT values.
        """
        cols_raw = self.db.execute(f'DESCRIBE "{table_name}"').fetchall()
        columns = []

        for col_name, col_type, *_ in cols_raw:
            col_info: dict = {
                "name": col_name,
                "type": col_type,
                "null_count": 0,
                "samples": [],
            }

            try:
                # Null count — single fast COUNT
                null_count = self.db.execute(
                    f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col_name}" IS NULL'
                ).fetchone()[0]
                col_info["null_count"] = null_count

                # Smart sampling: Get all sheet names, up to 10 for low-cardinality, or 3 for high-cardinality
                limit_clause = "LIMIT 3"
                if col_name == "Sheet_Name":
                    limit_clause = "" # Get all sheets so LLM knows exactly what's available
                
                raw_samples = self.db.execute(
                    f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                    f'WHERE "{col_name}" IS NOT NULL {limit_clause}'
                ).fetchall()
                col_info["samples"] = [str(r[0]) for r in raw_samples]

                type_up = col_type.upper()

                # ── Numeric columns ──────────────────────────────────────────
                if any(t in type_up for t in (
                    "INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC",
                    "BIGINT", "HUGEINT", "REAL", "TINYINT", "SMALLINT",
                )):
                    row = self.db.execute(
                        f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                        f'APPROX_COUNT_DISTINCT("{col_name}") FROM "{table_name}"'
                    ).fetchone()
                    if row:
                        col_info["min"] = row[0]
                        col_info["max"] = row[1]
                        col_info["distinct_count"] = row[2]

                # ── Date / timestamp columns ──────────────────────────────────
                elif any(t in type_up for t in ("DATE", "TIMESTAMP", "TIME")):
                    row = self.db.execute(
                        f'SELECT MIN("{col_name}"), MAX("{col_name}") FROM "{table_name}"'
                    ).fetchone()
                    if row:
                        col_info["min_date"] = str(row[0])
                        col_info["max_date"] = str(row[1])

                # ── Text / categorical columns ────────────────────────────────
                elif any(t in type_up for t in ("VARCHAR", "TEXT", "STRING", "CHAR")):
                    distinct = self.db.execute(
                        f'SELECT APPROX_COUNT_DISTINCT("{col_name}") FROM "{table_name}"'
                    ).fetchone()[0]
                    col_info["distinct_count"] = distinct
                    
                    # If it's a low cardinality column (not Sheet_Name, since that's already fetched), fetch up to 10 samples
                    if distinct <= 10:
                        col_info["cardinality"] = "low"      # ideal for pie / colour encoding
                        if col_name != "Sheet_Name":
                            raw_samples_ext = self.db.execute(
                                f'SELECT DISTINCT "{col_name}" FROM "{table_name}" '
                                f'WHERE "{col_name}" IS NOT NULL LIMIT 10'
                            ).fetchall()
                            col_info["samples"] = [str(r[0]) for r in raw_samples_ext]
                    elif distinct <= 50:
                        col_info["cardinality"] = "medium"   # ok for bar groupby
                    else:
                        col_info["cardinality"] = "high"     # avoid pie; use Top-N for bar

            except Exception:
                pass  # Skip stats for problematic columns; name/type still available

            columns.append(col_info)

        return {
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
        }

    # ── Session / lookup ──────────────────────────────────────────────────────

    def get_summary(self, dataset_id: str) -> dict:
        """Return dataset metadata.

        Raises 'session_expired:{id}' if the dataset is gone and cannot be
        recovered from disk (i.e. the Render container restarted).
        Silently re-ingests if the DuckDB table is missing but the file is present.
        """
        if dataset_id not in self.datasets:
            raise Exception(f"session_expired:{dataset_id}")

        table_name = self.datasets[dataset_id]["table_name"]
        # Verify the DuckDB table still exists
        try:
            self.db.execute(f'SELECT 1 FROM "{table_name}" LIMIT 1')
        except Exception:
            # Table gone — try to re-ingest from saved file
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
        table_name = info["table_name"]
        # Drop the old (potentially corrupt) table if it exists
        try:
            self.db.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        except Exception:
            pass
        self._load_into_duckdb(table_name, safe_path, info["file_ext"])
        # Refresh profile
        row_count = self.db.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        self.datasets[dataset_id]["profile"] = self._build_rich_profile(table_name, row_count)

    def get_rows(self, dataset_id: str, limit: int = 5000) -> list:
        if dataset_id not in self.datasets:
            return []
        table_name = self.datasets[dataset_id]["table_name"]
        result = self.db.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}').fetchall()
        columns = [desc[0] for desc in self.db.description]
        raw_rows = [{col: val for col, val in zip(columns, row)} for row in result]
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder(raw_rows)

    def execute_query(self, dataset_id: str, sql: str) -> list:
        """Execute a SELECT query against a dataset and return rows as dicts.

        Security: only SELECT statements are allowed.
        The placeholder {{table}} in the SQL is replaced with the actual table name.
        """
        if dataset_id not in self.datasets:
            raise Exception(f"Dataset '{dataset_id}' not found")
        if not sql.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are permitted")
        table_name = self.datasets[dataset_id]["table_name"]
        # The LLM sometimes wraps {{table}} in quotes. Strip them before substituting.
        safe_sql = sql.replace('\"{{table}}\"', "{{table}}").replace("\'{{table}}\'", "{{table}}")
        safe_sql = safe_sql.replace("{{table}}", f'"{table_name}"')
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
