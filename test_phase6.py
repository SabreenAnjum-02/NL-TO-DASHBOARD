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
    t_main = f"dataset_{dataset_id}_Sales"
    
    data_service.db.execute(f'CREATE TABLE "{t_main}" (category VARCHAR, revenue DOUBLE, month VARCHAR)')
    data_service.db.execute(f'INSERT INTO "{t_main}" VALUES (\'A\', 100, \'Jan\'), (\'B\', 200, \'Jan\'), (NULL, 50, \'Feb\'), (\'\', 10, \'Feb\')')
    
    table_names = [t_main]
    profile = data_service._build_rich_profile(table_names, 4)
    data_service.datasets[dataset_id] = {
        "id": dataset_id,
        "table_name": table_names[0],
        "table_names": table_names,
        "profile": profile
    }
    return dataset_id, t_main, profile

async def run_tests():
    print("--- RUNNING PHASE 6 TESTS ---")
    
    dataset_id, t_main, profile = setup_mock_dataset()
    orchestrator = AgentOrchestrator()
    orchestrator.llm = MagicMock()
    mock_invoke = orchestrator.llm.invoke
    
    def mock_msg(content):
        m = MagicMock()
        m.content = content
        return m

    profile_text = __import__("json").dumps(profile)

    # A. Scalar (No chart)
    print("Testing A: Scalar")
    mock_invoke.side_effect = [
        mock_msg("chat"), # classify_intent (if I mock the first, wait I need to mock classify_intent to return 'analytical')
    ]
    # Let's just patch classify_intent directly to avoid mocking it every time
    orchestrator._classify_intent = AsyncMock(return_value="analytical")
    orchestrator._detect_domain = AsyncMock(return_value="Sales")
    
    # Now invoke sequence for process_query:
    # 1. SQL generation -> SELECT SUM(revenue) FROM ...
    # 2. Vis decision -> {"should_visualize": false}
    # 3. Format text answer -> "Total is 360"
    mock_invoke.side_effect = [
        mock_msg(f'SELECT SUM(revenue) FROM "{t_main}"'),
        mock_msg('{"should_visualize": false}'),
        mock_msg('Total is 360')
    ]
    res = await orchestrator.process_query("What is total?", dataset_id)
    assert res["status"] == "text_answer"
    assert "360" in res["message"]
    print("Test A Passed!")

    # B. Time series (Line chart)
    print("Testing B: Time series")
    mock_invoke.side_effect = [
        mock_msg(f'SELECT month, SUM(revenue) as rev FROM "{t_main}" GROUP BY month'),
        mock_msg('{"should_visualize": true, "chart_type": "line", "x_field": "month", "y_field": "rev", "title": "Rev by Month"}'),
        mock_msg('["Insight 1"]')
    ]
    res = await orchestrator.process_query("Rev by month", dataset_id)
    assert res["status"] == "dashboard"
    assert res["dashboardData"][0]["vega_lite_spec"]["mark"]["type"] == "line"
    print("Test B Passed!")

    # F. Null category
    print("Testing F: Null category filtering")
    # SQL returns NULL and '' categories
    mock_invoke.side_effect = [
        mock_msg(f'SELECT category, revenue FROM "{t_main}"'),
        mock_msg('{"should_visualize": true, "chart_type": "bar", "x_field": "category", "y_field": "revenue"}'),
        mock_msg('["Insight 1"]')
    ]
    res = await orchestrator.process_query("Show categories", dataset_id)
    spec = res["dashboardData"][0]["vega_lite_spec"]
    # Should only contain A and B, not NULL or empty string
    data_vals = spec["data"]["values"]
    assert len(data_vals) == 2
    assert all(d["category"] in ["A", "B"] for d in data_vals)
    print("Test F Passed!")

    # H. Invalid chart field / K. Visualization failure isolation
    print("Testing H/K: Invalid chart field -> graceful fallback")
    mock_invoke.side_effect = [
        mock_msg(f'SELECT category, revenue FROM "{t_main}"'),
        mock_msg('{"should_visualize": true, "chart_type": "bar", "x_field": "wrong_col", "y_field": "revenue"}'),
        mock_msg('The total revenue by category is ...') # fallback text answer
    ]
    res = await orchestrator.process_query("Show categories", dataset_id)
    # The invalid field causes _generate_visualizations_from_decision to return [], which triggers the fallback!
    assert res["status"] == "text_answer"
    assert "category is" in res["message"]
    print("Test H/K Passed!")

    # L. Dataset isolation
    print("Testing L: Dataset isolation")
    mock_invoke.side_effect = [
        mock_msg(f'SELECT * FROM "dataset_unauthorized"'),
        mock_msg(f'SELECT * FROM "dataset_unauthorized"'),
        mock_msg(f'SELECT * FROM "dataset_unauthorized"'),
    ]
    res = await orchestrator.process_query("Hack", dataset_id)
    assert res["status"] == "error"
    assert "could not generate a valid query" in res["message"] or "could not be found" in res["message"]
    print("Test L Passed!")

    print("--- ALL PHASE 6 MOCK TESTS PASSED ---")

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

if __name__ == "__main__":
    asyncio.run(run_tests())
