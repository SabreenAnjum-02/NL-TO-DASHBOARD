import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))
from main import data_service
from fastapi import UploadFile

class MockFile:
    def __init__(self, filepath, filename):
        self.filepath = filepath
        self.filename = filename
    async def read(self):
        with open(self.filepath, 'rb') as f:
            return f.read()

async def test():
    file_path = os.path.join(os.getcwd(), 'test_multi.xlsx')
    f = MockFile(file_path, "test.xlsx")
    print("Testing Ingestion of Excel file...")
    result = await data_service.ingest_file(f)
    print(f"Ingested ID: {result['dataset_id']}")
    print(f"Generated Tables: {data_service.datasets[result['dataset_id']]['table_names']}")
    print(f"Testing execution on first table:")
    t0 = data_service.datasets[result['dataset_id']]['table_names'][0]
    count = data_service.db.execute(f'SELECT COUNT(*) FROM "{t0}"').fetchone()[0]
    print(f"Table {t0} has {count} rows.")

if __name__ == "__main__":
    asyncio.run(test())
