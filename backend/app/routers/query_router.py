"""
Query Router - Handles natural language queries from the user.
Processes NL input through the agent pipeline and returns dashboard specs.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class NLQueryRequest(BaseModel):
    """Natural language query from the user"""
    query: str
    dataset_id: str
    context: Optional[str] = None  # Previous conversation context


class ClarificationResponse(BaseModel):
    """User's response to a clarification question"""
    original_query: str
    clarification: str
    dataset_id: str


@router.post("/ask")
async def ask_query(request: NLQueryRequest):
    """
    Main endpoint: Accept a natural language query and return dashboard specifications.
    
    Pipeline:
    1. Ambiguity Detection → may return clarification questions
    2. Domain Detection → identifies business context
    3. Task Planning → creates DAG of sub-tasks
    4. Code Generation → produces Vega-Lite specs
    5. Self-Correction → validates and fixes specs
    6. Insight Generation → produces business insights
    """
    try:
        from app.agents.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()
        result = await orchestrator.process_query(
            query=request.query,
            dataset_id=request.dataset_id,
            context=request.context,
        )
        return JSONResponse(content=result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        if "GEMINI_API_KEY" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="AI service not configured. Please set your GEMINI_API_KEY in backend/.env"
            )
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/clarify")
async def handle_clarification(response: ClarificationResponse):
    """
    Handle user's response to a clarification question.
    Re-processes the query with additional context.
    """
    try:
        from app.agents.orchestrator import AgentOrchestrator
        orchestrator = AgentOrchestrator()
        result = await orchestrator.process_query(
            query=f"{response.original_query} (Clarification: {response.clarification})",
            dataset_id=response.dataset_id,
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
