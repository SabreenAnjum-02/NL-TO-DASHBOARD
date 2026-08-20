# DataSense AI Backend - Consolidated Entry Point
"""
A single FastAPI entry point that combines all routers, services, and the agent orchestrator.
It also adds PDF upload support via pdfplumber.
"""

import os
import uuid
import tempfile
import json
from typing import Optional

import duckdb
import pdfplumber
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables (Gemini API key)
load_dotenv()

app = FastAPI(
    title="DataSense AI API",
    description="Natural Language to Dashboard Generation - Agentic AI Backend",
    version="1.0.0",
)

# CORS for Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://nl-to-dashboard.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Data Service (Singleton) ----------
class DataService:
    """Manages data ingestion, storage, and profiling via DuckDB (Singleton)"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.db = duckdb.connect(":memory:")
        self.datasets = {}
        self._initialized = True

    async def ingest_file(self, file: UploadFile) -> dict:
        """Ingest CSV, Excel, JSON, Parquet **or PDF** files into DuckDB.
        For PDFs we attempt to extract the first table on the first page.
        """
        dataset_id = str(uuid.uuid4())[:8]
        file_ext = "." + file.filename.rsplit(".", 1)[-1].lower()
        # Save to temporary location
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        table_name = f"dataset_{dataset_id}"
        safe_path = temp_path.replace("\\", "/")
        try:
            if file_ext == ".csv":
                self.db.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{safe_path}')")
            elif file_ext in [".xlsx", ".xls"]:
                import pandas as pd
                dfs = pd.read_excel(safe_path, sheet_name=None)
                all_dfs = []
                for sheet, d in dfs.items():
                    # SMART FILTER: Skip instruction manuals, summary dashboards, and master lists
                    # which confuse the AI with non-transactional text
                    lower_name = sheet.lower()
                    if "how to" in lower_name or "dashboard" in lower_name or "master" in lower_name:
                        continue
                    
                    # Clean up: Drop completely empty rows and columns
                    d = d.dropna(how='all').dropna(axis=1, how='all')
                    if len(d) == 0:
                        continue
                        
                    # Ensure column names are clean strings
                    d.columns = [str(c).strip().replace('\n', ' ') for c in d.columns]
                    
                    d['Sheet_Name'] = sheet  # Add sheet name so AI knows where data came from
                    all_dfs.append(d)
                
                if not all_dfs:
                    df = pd.DataFrame({"Error": ["No valid data tables found in Excel"]})
                else:
                    # Concatenate only the clean data sheets
                    df = pd.concat(all_dfs, ignore_index=True)
                    # Fill missing values with empty strings so DuckDB can handle the mixed columns gracefully
                    df = df.fillna("")
                
                self.db.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
            elif file_ext == ".json":
                self.db.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_json_auto('{safe_path}')")
            elif file_ext == ".parquet":
                self.db.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{safe_path}')")
            elif file_ext == ".pdf":
                # Extract first table from first page using pdfplumber
                with pdfplumber.open(safe_path) as pdf:
                    page = pdf.pages[0]
                    table = page.extract_table()
                    if not table:
                        raise Exception("No table found in PDF")
                # Convert extracted table to CSV in-memory and load via DuckDB
                import csv, io
                csv_buf = io.StringIO()
                csv_writer = csv.writer(csv_buf)
                for row in table:
                    csv_writer.writerow(row)
                csv_buf.seek(0)
                # Load via DuckDB from the temporary CSV file we already have (safe_path still points to PDF, so use CSV buffer technique)
                # Write the CSV buffer to a temporary CSV file then load
                csv_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
                csv_temp.write(csv_buf.getvalue().encode())
                csv_temp.close()
                csv_path = csv_temp.name.replace("\\", "/")
                self.db.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{csv_path}')")
                os.unlink(csv_path)
            else:
                raise Exception(f"Unsupported file type: {file_ext}")
            # Simple profiling
            row_count = self.db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            columns = self.db.execute(f"DESCRIBE {table_name}").fetchall()
            col_names = [c[0] for c in columns]
            profile = {"row_count": row_count, "column_count": len(columns), "columns": col_names}
            self.datasets[dataset_id] = {"id": dataset_id, "filename": file.filename, "table_name": table_name, "profile": profile}
            return {"dataset_id": dataset_id, "filename": file.filename, "profile": profile, "status": "success"}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _profile_dataset(self, table_name: str) -> dict:
        row_count = self.db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        columns = self.db.execute(f"DESCRIBE {table_name}").fetchall()
        col_names = [c[0] for c in columns]
        return {"row_count": row_count, "column_count": len(columns), "columns": col_names}

    def get_summary(self, dataset_id: str) -> dict:
        if dataset_id not in self.datasets:
            raise Exception(f"Dataset '{dataset_id}' not found")
        return self.datasets[dataset_id]

    def get_rows(self, dataset_id: str, limit: int = 5000) -> list:
        if dataset_id not in self.datasets:
            return []
        table_name = self.datasets[dataset_id]["table_name"]
        result = self.db.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchall()
        columns = [desc[0] for desc in self.db.description]
        raw_rows = [{col: val for col, val in zip(columns, row)} for row in result]
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder(raw_rows)

    def list_datasets(self) -> dict:
        return {"datasets": [{"id": ds["id"], "filename": ds.get("filename"), "rows": ds["profile"]["row_count"], "columns": ds["profile"]["column_count"]} for ds in self.datasets.values()]}

# Instantiate singleton
data_service = DataService()

# ---------- API Endpoints (merged) ----------
@app.get("/")
async def root():
    return {"name": "DataSense AI API", "version": "1.0.0", "status": "running", "docs": "/docs"}

@app.get("/health")
async def health_check():
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    return {"status": "healthy", "llm_configured": bool(gemini_key)}

# Upload endpoint (supports PDF)
@app.post("/api/data/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    allowed = [".csv", ".xlsx", ".xls", ".json", ".parquet", ".pdf"]
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    result = await data_service.ingest_file(file)
    return JSONResponse(content=result)

# Stub endpoint for SQL connect – currently returns a placeholder response
@app.post("/api/data/connect-sql")
async def connect_sql(payload: dict):
    connection_string = payload.get("connection_string")
    table_name = payload.get("table_name")
    # In a full implementation we would connect to the DB and load a table.
    # For now we simply acknowledge the request.
    return JSONResponse(content={
        "status": "success",
        "message": "SQL connection stub – not implemented",
        "connection_string": connection_string,
        "table_name": table_name,
    })
@app.get("/api/data/datasets")
async def list_datasets():
    return JSONResponse(content=data_service.list_datasets())

@app.get("/api/data/summary/{dataset_id}")
async def get_summary(dataset_id: str):
    return JSONResponse(content=data_service.get_summary(dataset_id))

@app.get("/api/data/rows/{dataset_id}")
async def get_rows(dataset_id: str, limit: int = Query(default=5000, le=10000)):
    try:
        rows = data_service.get_rows(dataset_id, limit)
        return JSONResponse(content={"rows": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse(content={"rows": [], "count": 0, "error": str(e)}, status_code=200)

from app.routers import query_router
app.include_router(query_router.router, prefix="/api/query", tags=["Query"])

# End of consolidated backend
