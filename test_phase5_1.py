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
    t_detail = f"dataset_{dataset_id}_transactions"
    t_agg = f"dataset_{dataset_id}_monthly_summary"
    
    data_service.db.execute(f'CREATE TABLE "{t_detail}" (tx_id INT, amount DOUBLE)')
    data_service.db.execute(f'INSERT INTO "{t_detail}" VALUES (1, 100), (2, 200)')
    
    data_service.db.execute(f'CREATE TABLE "{t_agg}" (month VARCHAR, total_amount DOUBLE)')
    data_service.db.execute(f'INSERT INTO "{t_agg}" VALUES (\'Jan\', 300), (\'Feb\', 400)')
    
    table_names = [t_detail, t_agg]
    profile = data_service._build_rich_profile(table_names, 4)
    data_service.datasets[dataset_id] = {
        "id": dataset_id,
        "table_name": table_names[0],
        "table_names": table_names,
        "profile": profile
    }
    return dataset_id, t_detail, t_agg, profile

async def run_tests():
    print("--- RUNNING PHASE 5.1 TESTS ---")
    
    dataset_id, t_detail, t_agg, profile = setup_mock_dataset()
    orchestrator = AgentOrchestrator()
    orchestrator.llm = MagicMock()
    mock_invoke = orchestrator.llm.invoke
    
    def mock_sql(sql_query):
        m = MagicMock()
        m.content = sql_query
        return m

    # 1. Double-Counting Verification
    print("Testing Double-Counting Protection")
    # Simulate an LLM trying to sum over a JOIN of detail and summary tables.
    mock_invoke.side_effect = [
        mock_sql(f'SELECT SUM(d.amount + s.total_amount) FROM "{t_detail}" d JOIN "{t_agg}" s ON 1=1'),
        mock_sql(f'SELECT SUM(d.amount + s.total_amount) FROM "{t_detail}" d JOIN "{t_agg}" s ON 1=1'),
        mock_sql(f'SELECT SUM(d.amount + s.total_amount) FROM "{t_detail}" d JOIN "{t_agg}" s ON 1=1')
    ]
    profile_text = __import__('json').dumps(profile)
    res = await orchestrator._execute_and_format_query("Total revenue?", profile_text, dataset_id, "", "text")
    print(f"Result: {res}")
    assert "could not generate a valid query" in res
    print("Test Double-Counting Passed!")

    # 2. Zero-Result Aggregates
    print("Testing Zero-Result Aggregate (COUNT(*) = 0)")
    mock_invoke.side_effect = [
        mock_sql(f'SELECT COUNT(*) as c FROM "{t_detail}" WHERE amount > 9999'),
        mock_sql("The count is 0.")
    ]
    res = await orchestrator._execute_and_format_query("Count huge amounts", profile_text, dataset_id, "", "text")
    print(f"Result: {res}")
    assert "0" in res
    print("Test Zero-Result Aggregate Passed!")

    # 3. Retry Bound limit (Must not exceed 3 attempts)
    print("Testing Retry Bound = 3")
    mock_invoke.reset_mock()
    mock_invoke.side_effect = [
        mock_sql(f'SELECT * FROM "{t_detail}" WHERE 1=0'), # attempt 1
        mock_sql(f'SELECT * FROM "{t_detail}" WHERE 1=0'), # attempt 2
        mock_sql(f'SELECT * FROM "{t_detail}" WHERE 1=0'), # attempt 3
        mock_sql(f'SELECT * FROM "{t_detail}" WHERE 1=0')  # should not be called
    ]
    res = await orchestrator._execute_and_format_query("Trigger empty result", profile_text, dataset_id, "", "text")
    assert mock_invoke.call_count == 3
    assert "could not be found" in res
    print("Test Retry Bound Passed!")
    
    print("--- ALL PHASE 5.1 MOCK TESTS PASSED ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
