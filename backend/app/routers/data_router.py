"""
Data Router - Handles file uploads, SQL database connections, and data retrieval.
Supports CSV, Excel, JSON, Parquet, and SQL database ingestion.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Query
from fastapi.responses import JSONResponse
from app.services.data_service import DataService
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class SQLConnectionRequest(BaseModel):
    """Request model for SQL database connections"""
    connection_string: str
    table_name: Optional[str] = None


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a CSV or Excel file for analysis.
    The file is loaded into DuckDB for fast querying.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_extensions = [".csv", ".xlsx", ".xls", ".json", ".parquet"]
    file_ext = "." + file.filename.rsplit(".", 1)[-1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {allowed_extensions}",
        )

    try:
        data_service = DataService()  # Singleton — always the same instance
        result = await data_service.ingest_file(file)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect-sql")
async def connect_sql(request: SQLConnectionRequest):
    """
    Connect to an external SQL database (SQLite, PostgreSQL, MySQL).
    """
    try:
        data_service = DataService()
        result = await data_service.connect_sql_database(
            request.connection_string, request.table_name
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{dataset_id}")
async def get_data_summary(dataset_id: str):
    """
    Get the AI-generated summary/profile of a loaded dataset.
    """
    try:
        data_service = DataService()
        result = data_service.get_summary(dataset_id)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/rows/{dataset_id}")
async def get_data_rows(dataset_id: str, limit: int = Query(default=5000, le=10000)):
    """
    Get the actual data rows for a dataset.
    Used by the frontend to inject real data into Vega-Lite chart specs.
    """
    try:
        data_service = DataService()
        rows = data_service.get_rows(dataset_id, limit=limit)
        return JSONResponse(content={"rows": rows, "count": len(rows)})
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/datasets")
async def list_datasets():
    """List all currently loaded datasets"""
    data_service = DataService()
    return JSONResponse(content=data_service.list_datasets())
