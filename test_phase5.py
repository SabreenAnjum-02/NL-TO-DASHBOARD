import asyncio
import os
os.environ['OPENAI_API_KEY'] = 'dummy'
os.environ['ANTHROPIC_API_KEY'] = 'dummy'

import sys
import uuid
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.getcwd(), "backend"))
from main import data_service
from app.agents.orchestrator import AgentOrchestrator

def setup_mock_dataset():
    dataset_id = str(uuid.uuid4())[:8]
    t1 = f"dataset_{dataset_id}_Vendors"
    t2 = f"dataset_{dataset_id}_Orders"
    
    data_service.db.execute(f'CREATE TABLE "{t1}" (vendor_id VARCHAR, vendor_name VARCHAR, score INT)')
    data_service.db.execute(f'INSERT INTO "{t1}" VALUES (\'V1\', \'Alice\', 5), (\'V2\', \'Bob\', 4)')
    
    data_service.db.execute(f'CREATE TABLE "{t2}" (order_id INT, vendor_id VARCHAR, amount DOUBLE, order_date DATE)')
    data_service.db.execute(f'INSERT INTO "{t2}" VALUES (101, \'V1\', 150.5, \'2023-01-01\'), (102, \'V1\', 200.0, \'2023-01-02\'), (103, \'V2\', 50.0, \'2023-01-02\')')
    
    table_names = [t1, t2]
    profile = data_service._build_rich_profile(table_names, 2+3)
    data_service.datasets[dataset_id] = {
        "id": dataset_id,
        "table_name": table_names[0],
        "table_names": table_names,
        "profile": profile
    }
    return dataset_id, t1, t2

async def run_tests():
    print("--- RUNNING PHASE 5 TESTS ---")
    
    dataset_id, t_vendors, t_orders = setup_mock_dataset()
    orchestrator = AgentOrchestrator()
    orchestrator.llm = MagicMock()
    mock_invoke = orchestrator.llm.invoke
    
    def mock_sql(sql_query):
        m = MagicMock()
        m.content = sql_query
        return m
        
    def mock_error(msg):
        return Exception(msg)

    # Test B & F: Empty Result Diagnostic
    print("Testing B/F: Empty Result (Diagnostic retry)")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT * FROM "{t_vendors}" WHERE vendor_name = \'Nonexistent\''), # Returns 0 rows
        mock_sql(f'SELECT * FROM "{t_vendors}" WHERE vendor_name = \'Nonexistent\''), # Retry 1
        mock_sql(f'SELECT * FROM "{t_vendors}" WHERE vendor_name = \'Nonexistent\'')  # Retry 2
    ]
    res = await orchestrator._execute_and_format_query("Find Nonexistent", "{}", dataset_id, "", "table")
    print(f"Result: {res}")
    assert "could not be found in the uploaded data" in res
    print("Test B/F Passed!")

    # Test C & E: Malformed SQL / Wrong Column
    print("Testing C/E: Malformed SQL (DuckDB error)")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT wrong_col FROM "{t_vendors}"'), # Invalid column
        mock_sql(f'SELECT vendor_name FROM "{t_vendors}" LIMIT 1'), # Fixed
        mock_sql("The vendor is Alice.") # Format answer
    ]
    res = await orchestrator._execute_and_format_query("Who is vendor?", "{}", dataset_id, "", "text")
    print(f"Result: {res}")
    assert "Alice" in res
    print("Test C/E Passed!")

    # Test D: Wrong Table (Security Sandbox)
    print("Testing D: Wrong Table (Security Exception)")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT * FROM "dataset_unauthorized_123"'), # Banned
        mock_sql(f'SELECT * FROM "dataset_unauthorized_123"'),
        mock_sql(f'SELECT * FROM "dataset_unauthorized_123"')
    ]
    res = await orchestrator._execute_and_format_query("Hack", "{}", dataset_id, "", "table")
    print(f"Result: {res}")
    assert "could not generate a valid query" in res
    print("Test D Passed!")

    # Test G: Suspicious JOIN multiplication
    print("Testing G: Suspicious JOIN multiplication")
    # We simulate a bad join: SELECT * FROM t1 JOIN t2 ON 1=1
    mock_invoke.side_effect = [
        mock_sql(f'SELECT * FROM "{t_vendors}" JOIN "{t_orders}" ON 1=1'), # 2 * 3 = 6 rows (Max table is 3, 6 > 3*1.5 so suspicious)
        mock_sql(f'SELECT * FROM "{t_vendors}" JOIN "{t_orders}" ON 1=1'),
        mock_sql(f'SELECT * FROM "{t_vendors}" JOIN "{t_orders}" ON 1=1')
    ]
    # Max rows is 3. 3 * 2 = 6. 6 is not strictly > 6. Wait, the condition is `> (max_table_rows * 2)`.
    # Let me add a bunch of rows to t_vendors to guarantee multiplication triggers it.
    for i in range(10):
        data_service.db.execute(f'INSERT INTO "{t_vendors}" VALUES (\'VX{i}\', \'Ghost\', 1)')
    # Now max_rows is 12 (Vendors). 12 * 2 = 24.
    # Cross join: 12 * 3 = 36 rows! 36 > 24 -> Suspicious!
    mock_invoke.side_effect = [
        mock_sql(f'SELECT * FROM "{t_vendors}" JOIN "{t_orders}" ON 1=1'), # 36 rows
        mock_sql(f'SELECT * FROM "{t_vendors}" JOIN "{t_orders}" ON "{t_vendors}".vendor_id = "{t_orders}".vendor_id LIMIT 1'), # Fixed
        mock_sql("Corrected Join")
    ]
    profile = data_service._build_rich_profile([t_vendors, t_orders], 12+3)
    profile_text = __import__('json').dumps(profile)
    res = await orchestrator._execute_and_format_query("Cross join?", profile_text, dataset_id, "", "text")
    print(f"Result: {res}")
    assert "Corrected Join" in res
    print("Test G Passed!")

    # Provider Error Tests (I, J, K, L)
    print("Testing I: Provider 402")
    mock_invoke.side_effect = mock_error("openai.RateLimitError: 402 Payment Required: insufficient_quota")
    res = await orchestrator._execute_and_format_query("Test", "{}", dataset_id, "", "table")
    print(f"Result: {res}")
    assert "limit reached" in res
    print("Test I Passed!")
    
    print("Testing J: Provider 429")
    mock_invoke.side_effect = mock_error("429 Too many requests")
    res = await orchestrator._execute_and_format_query("Test", "{}", dataset_id, "", "table")
    print(f"Result: {res}")
    assert "rate limit reached" in res
    print("Test J Passed!")
    
    print("Testing K/L: Provider 500 / Timeout")
    mock_invoke.side_effect = mock_error("502 Bad Gateway")
    res = await orchestrator._execute_and_format_query("Test", "{}", dataset_id, "", "table")
    print(f"Result: {res}")
    assert "temporarily unavailable" in res
    
    mock_invoke.side_effect = mock_error("Connection timeout")
    res = await orchestrator._execute_and_format_query("Test", "{}", dataset_id, "", "table")
    print(f"Result: {res}")
    assert "timed out" in res
    print("Test K/L Passed!")

    print("--- ALL PHASE 5 MOCK TESTS PASSED ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
