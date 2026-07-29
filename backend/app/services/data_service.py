"""
Data Service - Core data ingestion, profiling, and storage using DuckDB.
Handles CSV/Excel uploads and SQL database connections.
Generates semantic data summaries for the LLM agents.

Uses a Singleton pattern so data persists across all API endpoints.
"""

import duckdb
import os
import uuid
import json
import tempfile
from typing import Optional
from fastapi import UploadFile


class DataService:
    """Manages data ingestion, storage, and profiling via DuckDB (Singleton)"""

    _instance = None

    def __new__(cls):
        """Singleton pattern — only one DataService exists across the entire app."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        # In-memory DuckDB for fast analytical queries
        self.db = duckdb.connect(":memory:")
        self.datasets = {}  # dataset_id -> metadata
        self._initialized = True

    async def ingest_file(self, file: UploadFile) -> dict:
        """
        Ingest an uploaded file (CSV, Excel, JSON, Parquet) into DuckDB.
        Returns dataset metadata including schema and basic statistics.
        """
        dataset_id = str(uuid.uuid4())[:8]
        file_ext = "." + file.filename.rsplit(".", 1)[-1].lower()

        # Save uploaded file temporarily
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)

        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Table name derived from filename
        table_name = f"dataset_{dataset_id}"

        # Normalize path for DuckDB (use forward slashes even on Windows)
        safe_path = temp_path.replace("\\", "/")

        try:
            # Load into DuckDB based on file type
            if file_ext == ".csv":
                self.db.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{safe_path}')"
                )
            elif file_ext in [".xlsx", ".xls"]:
                self.db.execute("INSTALL spatial; LOAD spatial;")
                self.db.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM st_read('{safe_path}')"
                )
            elif file_ext == ".json":
                self.db.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM read_json_auto('{safe_path}')"
                )
            elif file_ext == ".parquet":
                self.db.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{safe_path}')"
                )

            # Generate profile
            profile = self._profile_dataset(table_name)

            # Store metadata
            self.datasets[dataset_id] = {
                "id": dataset_id,
                "filename": file.filename,
                "table_name": table_name,
                "profile": profile,
            }

            return {
                "dataset_id": dataset_id,
                "filename": file.filename,
                "profile": profile,
                "status": "success",
            }
        except Exception as e:
            raise Exception(f"Failed to ingest file: {str(e)}")
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    async def connect_sql_database(
        self, connection_string: str, table_name: Optional[str] = None
    ) -> dict:
        """
        Connect to an external SQL database and import tables into DuckDB.
        Supports SQLite, PostgreSQL, MySQL connection strings.
        """
        dataset_id = str(uuid.uuid4())[:8]
        duckdb_table = f"dataset_{dataset_id}"

        try:
            if connection_string.startswith("sqlite"):
                # Extract SQLite file path
                db_path = connection_string.replace("sqlite:///", "").replace("\\", "/")
                self.db.execute(f"INSTALL sqlite; LOAD sqlite;")

                if table_name:
                    self.db.execute(
                        f"CREATE TABLE {duckdb_table} AS SELECT * FROM sqlite_scan('{db_path}', '{table_name}')"
                    )
                else:
                    # List all tables and import the first one
                    tables = self.db.execute(
                        f"SELECT name FROM sqlite_scan('{db_path}', 'sqlite_master') WHERE type='table'"
                    ).fetchall()
                    if not tables:
                        raise Exception("No tables found in the database")
                    table_name = tables[0][0]
                    self.db.execute(
                        f"CREATE TABLE {duckdb_table} AS SELECT * FROM sqlite_scan('{db_path}', '{table_name}')"
                    )

            elif connection_string.startswith("postgresql"):
                self.db.execute("INSTALL postgres; LOAD postgres;")
                self.db.execute(
                    f"CREATE TABLE {duckdb_table} AS SELECT * FROM postgres_scan('{connection_string}', '{table_name}')"
                )

            elif connection_string.startswith("mysql"):
                self.db.execute("INSTALL mysql; LOAD mysql;")
                self.db.execute(
                    f"CREATE TABLE {duckdb_table} AS SELECT * FROM mysql_scan('{connection_string}', '{table_name}')"
                )
            else:
                raise Exception(
                    f"Unsupported database type. Use sqlite, postgresql, or mysql."
                )

            profile = self._profile_dataset(duckdb_table)

            self.datasets[dataset_id] = {
                "id": dataset_id,
                "source": "sql",
                "connection_string": connection_string,
                "original_table": table_name,
                "table_name": duckdb_table,
                "profile": profile,
            }

            return {
                "dataset_id": dataset_id,
                "source_table": table_name,
                "profile": profile,
                "status": "success",
            }
        except Exception as e:
            raise Exception(f"Failed to connect to database: {str(e)}")

    def _profile_dataset(self, table_name: str) -> dict:
        """
        Generate a comprehensive statistical profile of the dataset.
        This summary is fed to the LLM for domain detection and goal exploration.
        """
        # Get column info
        columns_info = self.db.execute(
            f"DESCRIBE {table_name}"
        ).fetchall()

        # Get row count
        row_count = self.db.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]

        # Get sample rows (first 5)
        sample_rows = self.db.execute(
            f"SELECT * FROM {table_name} LIMIT 5"
        ).fetchall()

        column_names = [col[0] for col in columns_info]

        # Build column-level statistics
        column_stats = []
        for col_info in columns_info:
            col_name = col_info[0]
            col_type = col_info[1]

            stats = {
                "name": col_name,
                "type": col_type,
            }

            try:
                # Null count
                null_count = self.db.execute(
                    f'SELECT COUNT(*) FROM {table_name} WHERE "{col_name}" IS NULL'
                ).fetchone()[0]
                stats["null_count"] = null_count
                stats["null_percentage"] = round(
                    (null_count / row_count * 100) if row_count > 0 else 0, 2
                )

                # Unique count
                unique_count = self.db.execute(
                    f'SELECT COUNT(DISTINCT "{col_name}") FROM {table_name}'
                ).fetchone()[0]
                stats["unique_count"] = unique_count

                # For numeric columns: min, max, mean, std
                if "INT" in col_type.upper() or "FLOAT" in col_type.upper() or "DOUBLE" in col_type.upper() or "DECIMAL" in col_type.upper() or "NUMERIC" in col_type.upper() or "BIGINT" in col_type.upper():
                    numeric_stats = self.db.execute(
                        f'SELECT MIN("{col_name}"), MAX("{col_name}"), AVG("{col_name}"), STDDEV("{col_name}") FROM {table_name}'
                    ).fetchone()
                    stats["min"] = float(numeric_stats[0]) if numeric_stats[0] is not None else None
                    stats["max"] = float(numeric_stats[1]) if numeric_stats[1] is not None else None
                    stats["mean"] = round(float(numeric_stats[2]), 4) if numeric_stats[2] is not None else None
                    stats["std"] = round(float(numeric_stats[3]), 4) if numeric_stats[3] is not None else None

                # For categorical columns: top 5 values
                elif unique_count <= 50:
                    top_values = self.db.execute(
                        f'SELECT "{col_name}", COUNT(*) as cnt FROM {table_name} WHERE "{col_name}" IS NOT NULL GROUP BY "{col_name}" ORDER BY cnt DESC LIMIT 5'
                    ).fetchall()
                    stats["top_values"] = [
                        {"value": str(v[0]), "count": v[1]} for v in top_values
                    ]
            except Exception:
                pass  # Skip stats for complex types

            column_stats.append(stats)

        # Format sample rows as list of dicts
        sample_data = []
        for row in sample_rows:
            sample_data.append(
                {col_names: str(val) for col_names, val in zip(column_names, row)}
            )

        return {
            "row_count": row_count,
            "column_count": len(columns_info),
            "columns": column_stats,
            "sample_data": sample_data,
        }

    def get_summary(self, dataset_id: str) -> dict:
        """Get the stored profile/summary for a dataset"""
        if dataset_id not in self.datasets:
            raise Exception(f"Dataset '{dataset_id}' not found")
        return self.datasets[dataset_id]

    def get_rows(self, dataset_id: str, limit: int = 5000) -> list:
        """
        Get the actual data rows for a dataset.
        Used by the frontend to inject real data into Vega-Lite chart specs.
        Capped at `limit` rows for performance.
        """
        if dataset_id not in self.datasets:
            raise Exception(f"Dataset '{dataset_id}' not found")

        table_name = self.datasets[dataset_id]["table_name"]
        result = self.db.execute(
            f"SELECT * FROM {table_name} LIMIT {limit}"
        ).fetchall()
        columns = [desc[0] for desc in self.db.description]

        rows = []
        for row in result:
            row_dict = {}
            for col, val in zip(columns, row):
                # Convert non-serializable types to strings
                if val is None:
                    row_dict[col] = None
                elif isinstance(val, (int, float, bool)):
                    row_dict[col] = val
                else:
                    row_dict[col] = str(val)
            rows.append(row_dict)

        return rows

    def list_datasets(self) -> dict:
        """List all loaded datasets"""
        return {
            "datasets": [
                {
                    "id": ds["id"],
                    "filename": ds.get("filename", ds.get("original_table", "SQL")),
                    "rows": ds["profile"]["row_count"],
                    "columns": ds["profile"]["column_count"],
                }
                for ds in self.datasets.values()
            ]
        }

    def execute_query(self, dataset_id: str, sql: str) -> list:
        """Execute a raw SQL query against a loaded dataset"""
        if dataset_id not in self.datasets:
            raise Exception(f"Dataset '{dataset_id}' not found")

        table_name = self.datasets[dataset_id]["table_name"]
        # Replace placeholder table references with actual table name
        safe_sql = sql.replace("{{TABLE}}", table_name)

        result = self.db.execute(safe_sql).fetchall()
        columns = [desc[0] for desc in self.db.description]

        return [dict(zip(columns, row)) for row in result]
