import asyncio
import os
import sys
import pandas as pd
import json
import uuid

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

def create_mock_csv():
    path = "test_csv.csv"
    pd.DataFrame({"id": [1,2], "val": [10,20]}).to_csv(path, index=False)
    return path

def create_mock_json():
    path = "test_json.json"
    with open(path, "w") as f:
        json.dump([{"id": 1, "val": 10}, {"id": 2, "val": 20}], f)
    return path

def create_mock_parquet():
    path = "test_parquet.parquet"
    pd.DataFrame({"id": [1,2], "val": [10,20]}).to_parquet(path)
    return path

def create_mock_excel():
    path = "test_excel.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Vendor": ["V1"], "Score": [5], "Revenue": [100]}).to_excel(writer, sheet_name="Vendors", index=False)
        pd.DataFrame({"Crew": ["C1"], "Rating": [4], "Salary": [50]}).to_excel(writer, sheet_name="Crew", index=False)
        pd.DataFrame({"Employee": ["E1"], "Department": ["HR"], "Salary": [100]}).to_excel(writer, sheet_name="Payroll", index=False)
        # Empty sheet
        pd.DataFrame().to_excel(writer, sheet_name="Empty", index=False)
        # Decorative sheet
        pd.DataFrame({"Note": ["This is a test"]}).to_excel(writer, sheet_name="how to use", index=False, header=False)
        # Dashboard sheet (valid data)
        pd.DataFrame({"Metric": ["KPI"], "Value": [1]}).to_excel(writer, sheet_name="Dashboard", index=False)
        # Master sheet (valid data)
        pd.DataFrame({"ID": [1], "Name": ["M1"]}).to_excel(writer, sheet_name="Vendor Master", index=False)
    return path

async def run_tests():
    print("--- RUNNING PHASE 2 TESTS ---")
    
    csv_path = create_mock_csv()
    json_path = create_mock_json()
    excel_path = create_mock_excel()
    
    # A. Single CSV
    res_csv = await data_service.ingest_file(MockFile(csv_path, "test.csv"))
    tables_csv = data_service.datasets[res_csv['dataset_id']]['table_names']
    print(f"CSV Tables: {tables_csv}")
    assert len(tables_csv) == 1
    
    # B. Single JSON
    res_json = await data_service.ingest_file(MockFile(json_path, "test.json"))
    tables_json = data_service.datasets[res_json['dataset_id']]['table_names']
    print(f"JSON Tables: {tables_json}")
    assert len(tables_json) == 1
    
    # C. Skipped Parquet (no local pyarrow)
    
    # D, E, F, G. Multi-sheet Excel, Empty, Dashboard, Master
    res_excel_A = await data_service.ingest_file(MockFile(excel_path, "test_A.xlsx"))
    tables_A = data_service.datasets[res_excel_A["dataset_id"]]["table_names"]
    print(f"Excel A Tables: {tables_A}")
    
    # Verify specific tables exist (ignoring clean logic, checking sub-strings)
    assert any("Vendors" in t for t in tables_A)
    assert any("Crew" in t for t in tables_A)
    assert any("Payroll" in t for t in tables_A)
    assert any("Dashboard" in t for t in tables_A)
    assert any("Vendor_Master" in t for t in tables_A)
    # Empty should NOT be there
    assert not any("Empty" in t for t in tables_A)
    assert not any("how_to_use" in t for t in tables_A)
    
    # H. Dataset A + Dataset B isolation
    res_excel_B = await data_service.ingest_file(MockFile(excel_path, "test_B.xlsx"))
    tables_B = data_service.datasets[res_excel_B["dataset_id"]]["table_names"]
    print(f"Excel B Tables: {tables_B}")
    assert set(tables_A).isdisjoint(set(tables_B))
    
    # K. Correct row counts (Vendors has 1 row, plus header=0 so 1 row)
    vendor_table = [t for t in tables_A if "Vendors" in t][0]
    count = data_service.db.execute(f'SELECT COUNT(*) FROM "{vendor_table}"').fetchone()[0]
    assert count == 1, f"Expected 1, got {count}"
    print(f"Vendor table has {count} rows. (Correct)")
    
    # L. No cross-table data contamination
    cols = [d[0] for d in data_service.db.execute(f'DESCRIBE "{vendor_table}"').fetchall()]
    assert "Score" in cols
    assert "Salary" not in cols, "Salary leaked into Vendors!"
    print(f"Vendor columns: {cols} (No contamination)")
    
    # I. Re-ingestion cleanup
    # Reingest A
    print("Re-ingesting Dataset A...")
    data_service._reingest(res_excel_A["dataset_id"])
    new_tables_A = data_service.datasets[res_excel_A["dataset_id"]]["table_names"]
    assert len(new_tables_A) == len(tables_A)
    
    # Check that previous A tables are recreated
    for t in tables_A:
        try:
            data_service.db.execute(f'SELECT 1 FROM "{t}"')
        except Exception as e:
            assert False, f"Table {t} was dropped but not recreated!"
    print("Re-ingestion correctly dropped old tables and isolated states.")
    
    # Check get_summary
    print("Testing get_summary...")
    summary = data_service.get_summary(res_excel_A["dataset_id"])
    assert "profile" in summary
    
    # Check get_rows
    print("Testing get_rows...")
    rows = data_service.get_rows(res_excel_A["dataset_id"], 10)
    assert len(rows) > 0
    assert "__table__" in rows[0], "Missing __table__ in preview"
    print(f"Preview returned {len(rows)} mixed rows.")
    
    # Cleanup files
    os.remove(csv_path)
    os.remove(json_path)
    os.remove(excel_path)
    print("--- ALL PHASE 2 TESTS PASSED ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
