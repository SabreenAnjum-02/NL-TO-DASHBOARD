import asyncio
import os
import sys
import uuid
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.getcwd(), "backend"))
from main import data_service
from app.agents.orchestrator import AgentOrchestrator

def setup_mock_dataset():
    dataset_id = str(uuid.uuid4())[:8]
    t1 = f"dataset_{dataset_id}_Vendors"
    t2 = f"dataset_{dataset_id}_Crew"
    t3 = f"dataset_{dataset_id}_Orders"
    
    # Create test tables
    data_service.db.execute(f'CREATE TABLE "{t1}" (vendor_id VARCHAR, vendor_name VARCHAR, score INT)')
    data_service.db.execute(f'INSERT INTO "{t1}" VALUES (\'V1\', \'Alice\', 5), (\'V2\', \'Bob\', 4)')
    
    data_service.db.execute(f'CREATE TABLE "{t2}" (crew_id VARCHAR, crew_name VARCHAR, rating INT)')
    data_service.db.execute(f'INSERT INTO "{t2}" VALUES (\'C1\', \'Charlie\', 3), (\'C2\', \'Dave\', 2)')
    
    data_service.db.execute(f'CREATE TABLE "{t3}" (order_id INT, vendor_id VARCHAR, amount DOUBLE, order_date DATE)')
    data_service.db.execute(f'INSERT INTO "{t3}" VALUES (101, \'V1\', 150.5, \'2023-01-01\'), (102, \'V1\', 200.0, \'2023-01-02\'), (103, \'V2\', 50.0, \'2023-01-02\')')
    
    table_names = [t1, t2, t3]
    profile = data_service._build_rich_profile(table_names, 2+2+3)
    data_service.datasets[dataset_id] = {
        "id": dataset_id,
        "table_name": table_names[0],
        "table_names": table_names,
        "profile": profile
    }
    return dataset_id, t1, t2, t3

async def run_tests():
    print("--- RUNNING PHASE 4 TESTS ---")
    
    dataset_id, t_vendors, t_crew, t_orders = setup_mock_dataset()
    orchestrator = AgentOrchestrator()
    
    def mock_sql(sql_query):
        mock_response = MagicMock()
        mock_response.content = sql_query
        return mock_response
        
    orchestrator.llm = MagicMock()
    mock_invoke = orchestrator.llm.invoke
    
    # Test A: Single-table query
    print("Testing A: Single-table query")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT AVG(score) as avg_score FROM "{t_vendors}"'),
        mock_sql("The average vendor score is 4.5.")
    ]
    res = await orchestrator._execute_and_format_query(
        "What is the average vendor score?",
        "dummy_profile",
        dataset_id,
        "",
        "text"
    )
    print(f"Result: {res}")
    assert "4.5" in res
    print("Test A Passed!")
    
    # Test B: Similar column names
    print("Testing B: Similar column names")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT vendor_name, score FROM "{t_vendors}" ORDER BY score DESC LIMIT 1'),
        mock_sql("Alice has the highest score of 5.")
    ]
    res = await orchestrator._execute_and_format_query(
        "Which vendors have the highest scores?",
        "dummy_profile",
        dataset_id,
        "",
        "text"
    )
    print(f"Result: {res}")
    assert "Alice" in res
    print("Test B Passed!")
    
    # Test C: Multi-table relationship
    print("Testing C: Multi-table relationship")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT v.vendor_name, SUM(o.amount) as total FROM "{t_vendors}" v JOIN "{t_orders}" o ON v.vendor_id = o.vendor_id GROUP BY v.vendor_name ORDER BY total DESC'),
        mock_sql("Alice has 350.5 and Bob has 50.0 total order value.")
    ]
    res = await orchestrator._execute_and_format_query(
        "What is total order value by vendor?",
        "dummy_profile",
        dataset_id,
        "",
        "text"
    )
    print(f"Result: {res}")
    assert "350.5" in res
    print("Test C Passed!")
    
    # Test E: Dataset isolation protection
    print("Testing E: Dataset isolation")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT * FROM "dataset_unauthorized_1234_Secret"'),
        mock_sql(f'SELECT * FROM "dataset_unauthorized_1234_Secret"') # retry returns same bad query
    ]
    res = await orchestrator._execute_and_format_query(
        "Show me secrets",
        "dummy_profile",
        dataset_id,
        "",
        "table"
    )
    print(f"Result (Expected Error): {res}")
    assert "Security violation" in res
    print("Test E Passed!")

    print("--- ALL PHASE 4 MOCK TESTS PASSED ---")
    print("Note: LLM responses were deterministically mocked as OpenRouter credits are unavailable.")

if __name__ == "__main__":
    asyncio.run(run_tests())
