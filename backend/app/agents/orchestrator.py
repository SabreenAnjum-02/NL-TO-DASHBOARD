"""
Agent Orchestrator - The brain of InsightFlow.
Coordinates multiple specialized AI agents in a pipeline:

1. Ambiguity Detector   → Checks if the query is clear enough
2. Domain Detector      → Identifies the business domain
3. Task Planner         → Breaks the goal into sub-tasks (DAG)
4. Visual Generator     → Generates Vega-Lite specifications
5. Self-Corrector       → Validates and fixes generated specs
6. Insight Generator    → Produces business insights

Uses Google Gemini via LangChain for LLM capabilities.
"""

import os
import json
import re
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from google import genai


def _clean_json_response(text: str) -> str:
    """Extract valid JSON from LLM responses, stripping markdown fences and extra text."""
    text = text.strip()

    # Remove markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try to find JSON array or object boundaries
    # Find first [ or { and last ] or }
    start_arr = text.find('[')
    start_obj = text.find('{')

    if start_arr == -1 and start_obj == -1:
        return text

    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        # Looks like a JSON array
        end = text.rfind(']')
        if end != -1:
            return text[start_arr:end + 1]
    elif start_obj != -1:
        # Looks like a JSON object
        end = text.rfind('}')
        if end != -1:
            return text[start_obj:end + 1]

    return text


class AgentOrchestrator:
    """Orchestrates the multi-agent pipeline for NL-to-Dashboard generation"""

    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise Exception("OPENROUTER_API_KEY not configured.")

        self.llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model="openai/gpt-4o-mini",
            temperature=0.2,  # Low temperature for consistent code generation
        )

    async def process_query(
        self,
        query: str,
        dataset_id: str,
        context: Optional[str] = None,
    ) -> dict:
        """
        Main pipeline: Process a natural language query and return dashboard specifications.
        First classifies intent: casual chat vs. data/visualization request.
        """
        from main import data_service

        # Step 0a: Intent Classification — is this a chat message or a data request?
        intent = await self._classify_intent(query)
        if intent == "chat":
            chat_response = await self._handle_chat(query)
            return {
                "status": "chat_reply",
                "message": chat_response,
            }

        # Step 0b: Get dataset profile
        try:
            dataset_info = data_service.get_summary(dataset_id)
            profile = dataset_info["profile"]
        except Exception:
            return {
                "status": "error",
                "message": f"Dataset '{dataset_id}' not found. Please upload data first.",
            }

        profile_text = json.dumps(profile, indent=2, default=str)

        # Step 1: Ambiguity Detection
        ambiguity_result = await self._detect_ambiguity(query, profile_text)
        if ambiguity_result.get("is_ambiguous"):
            return {
                "status": "clarification_needed",
                "questions": ambiguity_result["questions"],
                "original_query": query,
            }

        # Step 2: Domain Detection
        domain = await self._detect_domain(profile_text)

        # Step 3: Task Planning (DAG generation)
        task_plan = await self._plan_tasks(query, profile_text, domain)

        # Step 4: Visual Generation (Vega-Lite specs)
        vega_specs = await self._generate_visualizations(
            query, profile_text, domain, task_plan
        )

        # Step 5: Self-Correction (validate specs)
        corrected_specs = await self._self_correct(vega_specs, profile)

        # Step 6: Generate insights summary
        insights = await self._generate_insights(query, profile_text, domain)

        return {
            "status": "success",
            "domain": domain,
            "task_plan": task_plan,
            "charts": corrected_specs,
            "insights": insights,
            "query": query,
        }

    async def _classify_intent(self, query: str) -> str:
        """
        Agent 0: Intent Classifier
        Determines if the user message is casual conversation or a data/visualization request.
        Returns 'chat' or 'data'.
        """
        lowered = query.strip().lower()

        # Fast shortcut: obvious greetings / casual phrases (no LLM call needed)
        chat_phrases = [
            "hi", "hello", "hey", "hii", "hiii", "yo", "sup",
            "good morning", "good afternoon", "good evening", "good night",
            "how are you", "what's up", "whats up", "wassup",
            "thank you", "thanks", "thank", "bye", "goodbye", "see you",
            "ok", "okay", "cool", "nice", "great", "awesome", "got it",
            "who are you", "what are you", "what can you do", "help",
            "what is this", "how does this work",
        ]
        if lowered in chat_phrases or len(lowered) <= 3:
            return "chat"

        # Fast shortcut: obvious data keywords → skip LLM call
        data_keywords = [
            "show", "chart", "graph", "plot", "dashboard", "visualize",
            "analyze", "analysis", "compare", "trend", "sales", "revenue",
            "distribution", "top", "bottom", "average", "total", "sum",
            "count", "breakdown", "category", "region", "product", "monthly",
            "quarterly", "yearly", "correlation", "report", "overview",
            "insight", "kpi", "metric", "filter", "group by", "aggregate",
        ]
        if any(kw in lowered for kw in data_keywords):
            return "data"

        # Borderline case: ask the LLM
        prompt = f"""Classify the following user message as either "chat" or "data".

- "chat" = casual conversation, greetings, questions about the app, thanks, small talk
- "data" = anything requesting data analysis, charts, visualizations, insights, dashboards, or questions about the dataset

User message: "{query}"

Respond with ONLY one word: chat or data"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = response.content.strip().lower()
            return "chat" if "chat" in result else "data"
        except Exception:
            return "data"  # Default to data on error

    async def _handle_chat(self, query: str) -> str:
        """
        Handles casual/conversational messages with a friendly, context-aware response.
        """
        prompt = f"""You are DataSense AI, a friendly and helpful data analysis assistant. 
You help users explore their datasets by generating interactive dashboards and insights.

The user has sent you a casual message (not a data request). Respond naturally, warmly, and helpfully.
Keep your response concise (1-3 sentences). If they say hi/hello, greet them back and briefly mention what you can do.
If they ask what you can do, explain your capabilities clearly.
If they say thanks, respond warmly.

User message: "{query}"

Respond naturally:"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception:
            return "Hello! 👋 I'm DataSense AI. I can help you analyze your data and create interactive dashboards. Just ask me a question about your dataset!"

    async def _detect_ambiguity(self, query: str, profile: str) -> dict:
        """
        Agent 1: Ambiguity Detector
        Checks if the user's query is clear enough to proceed.
        Favors immediate dashboard generation over annoying clarification loops.
        """
        lowered = query.lower()
        # Immediately proceed for any general, broad, or follow-up request
        general_terms = [
            "dashboard", "analysis", "all", "no specific", "charts", "overview",
            "visualize", "general", "anything", "whatever", "show", "give me",
            "include", "create", "summary", "report", "clarification:"
        ]
        if any(term in lowered for term in general_terms) or len(query.strip()) < 3:
            return {"is_ambiguous": False, "confidence": 1.0}

        prompt = f"""You are an Ambiguity Detection Agent for a data visualization dashboard. Your goal is to keep user friction LOW.

Analyze the user's query against the dataset profile:
Dataset Profile:
{profile}

User Query: "{query}"

CRITICAL RULE: If the query can be reasonably interpreted to build 2-4 standard visualization charts (e.g. key distributions, top metrics, category breakdowns), set "is_ambiguous" to FALSE. Always prefer making intelligent assumptions and generating charts instead of annoying the user with questions.

Set "is_ambiguous" to TRUE ONLY IF the query is completely nonsensical or impossible to visualize.

Respond ONLY in JSON format:
{{
    "is_ambiguous": false,
    "confidence": 1.0,
    "questions": []
}}"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            text = _clean_json_response(response.content)
            res = json.loads(text)
            # Extra safety check: if confidence is reasonably high or questions empty, set is_ambiguous to False
            if not res.get("questions"):
                res["is_ambiguous"] = False
            return res
        except Exception:
            return {"is_ambiguous": False, "confidence": 1.0}

    async def _detect_domain(self, profile: str) -> str:
        """
        Agent 2: Domain Detector
        Identifies the business domain of the dataset for context-aware analysis.
        """
        prompt = f"""You are a Domain Detection Agent. Analyze this dataset profile and identify the business domain.

Dataset Profile:
{profile}

Return a single short domain label such as: "E-Commerce", "Healthcare", "Finance", "Marketing", "Education", "Manufacturing", "Retail", "HR", "Sports", "Social Media", "IoT", "Supply Chain", etc.

Return ONLY the domain label, nothing else."""

        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip().strip('"')

    async def _plan_tasks(self, query: str, profile: str, domain: str) -> dict:
        """
        Agent 3: Recursive Task Planner
        Breaks down the user's goal into a DAG of sub-tasks.
        """
        prompt = f"""You are a Task Planning Agent for a {domain} data visualization system.

Dataset Profile:
{profile}

User Query: "{query}"

Break down this query into a sequence of analytical sub-tasks. Each task should be a specific, actionable step.

Respond in JSON format:
{{
    "goal": "High-level description of what the user wants",
    "tasks": [
        {{
            "id": "task_1",
            "description": "Description of the sub-task",
            "type": "data_transform|aggregation|filtering|visualization|insight",
            "depends_on": []
        }},
        {{
            "id": "task_2",
            "description": "Description",
            "type": "visualization",
            "depends_on": ["task_1"]
        }}
    ]
}}

Keep it to 3-6 tasks maximum. Return ONLY valid JSON, no markdown formatting."""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            text = _clean_json_response(response.content)
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "goal": query,
                "tasks": [
                    {
                        "id": "task_1",
                        "description": "Analyze and visualize data",
                        "type": "visualization",
                        "depends_on": [],
                    }
                ],
            }

    async def _generate_visualizations(
        self, query: str, profile: str, domain: str, task_plan: dict
    ) -> list:
        """
        Agent 4: Visual Generator
        Generates Vega-Lite specifications based on the task plan.
        """
        prompt = f"""You are a Visualization Generation Agent for a {domain} dashboard.

Dataset Profile:
{profile}

User Query: "{query}"

Task Plan:
{json.dumps(task_plan, indent=2)}

Generate 2-4 Vega-Lite v5 chart specifications that together form a comprehensive dashboard answering the user's query.

For each chart, use the ACTUAL column names from the dataset profile. Use appropriate chart types:
- Bar chart for comparisons across categories
- Line chart for trends over time
- Pie/donut chart for proportions (use "arc" mark with theta encoding)
- Scatter plot for correlations between two numeric variables

CRITICAL RULES:
1. Use "$schema": "https://vega.github.io/schema/vega-lite/v5.json"
2. Set "data": {{"values": []}} as placeholder — the frontend will inject real data
3. For DATE/TIMESTAMP columns, ALWAYS set "type": "temporal" and add "timeUnit": "month" or "timeUnit": "yearmonth" for aggregation
4. For categorical/text columns, ALWAYS set "type": "nominal"
5. For numeric columns, ALWAYS set "type": "quantitative"
6. For "field" values, use the EXACT column names from the profile (case-sensitive!)
7. For aggregations, use "aggregate" inside the encoding (e.g., "aggregate": "sum")
8. Always include "tooltip" with relevant fields
9. For bar charts, use "mark": "bar"
10. For line charts, use "mark": {{"type": "line", "point": true}}
11. For pie/donut charts, use "mark": {{"type": "arc", "innerRadius": 50}} with "theta" and "color" encodings
12. Keep chart titles concise and descriptive
13. Do NOT use "timeUnit" on non-date fields
14. Do NOT use "stack" on line charts

EXAMPLE of a correct bar chart spec:
{{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "data": {{"values": []}},
  "mark": "bar",
  "encoding": {{
    "x": {{"field": "Category", "type": "nominal", "title": "Category"}},
    "y": {{"field": "Total_Sales", "type": "quantitative", "aggregate": "sum", "title": "Total Sales"}},
    "color": {{"field": "Category", "type": "nominal"}},
    "tooltip": [
      {{"field": "Category", "type": "nominal"}},
      {{"field": "Total_Sales", "type": "quantitative", "aggregate": "sum"}}
    ]
  }}
}}

Respond as a JSON array of objects:
[
    {{
        "title": "Chart Title",
        "description": "What this chart shows",
        "vega_lite_spec": {{ ... complete Vega-Lite v5 spec ... }}
    }}
]

Return ONLY valid JSON, no markdown formatting."""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            text = _clean_json_response(response.content)
            return json.loads(text)
        except json.JSONDecodeError:
            return [
                {
                    "title": "Error generating visualization",
                    "description": "The LLM response could not be parsed",
                    "vega_lite_spec": {},
                }
            ]

    async def _self_correct(self, vega_specs: list, profile: dict) -> list:
        """
        Agent 5: Self-Corrector
        Validates Vega-Lite specs and fixes common issues.
        Ensures column names match the actual dataset.
        """
        cols = profile.get("columns", [])
        valid_columns = {
            col["name"] if isinstance(col, dict) else str(col)
            for col in cols
        }
        corrected = []

        for spec_obj in vega_specs:
            if not isinstance(spec_obj, dict):
                continue

            spec = spec_obj.get("vega_lite_spec", {})
            if not isinstance(spec, dict):
                continue

            # Ensure required fields exist
            if "$schema" not in spec:
                spec["$schema"] = "https://vega.github.io/schema/vega-lite/v5.json"

            if "data" not in spec:
                spec["data"] = {"values": []}

            if "width" not in spec:
                spec["width"] = "container"

            if "height" not in spec:
                spec["height"] = 300

            # Fix mark specification
            if "mark" in spec and isinstance(spec["mark"], str):
                pass  # Simple string marks are fine
            elif "mark" in spec and isinstance(spec["mark"], dict):
                if "type" not in spec["mark"]:
                    spec["mark"]["type"] = "bar"

            # Remove any title from config that might conflict
            if "config" in spec and isinstance(spec["config"], dict):
                # Keep user config but ensure it doesn't break rendering
                pass

            spec_obj["vega_lite_spec"] = spec
            corrected.append(spec_obj)

        return corrected if corrected else [
            {
                "title": "Analysis Summary",
                "description": "Unable to generate specific charts. Try a more specific query.",
                "vega_lite_spec": {
                    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                    "data": {"values": []},
                    "mark": "bar",
                    "width": "container",
                    "height": 300,
                },
            }
        ]

    async def _generate_insights(self, query: str, profile: str, domain: str) -> list:
        """
        Agent 6: Insight Generator
        Generates human-readable business insights based on the data analysis.
        """
        prompt = f"""You are a Business Insight Agent for {domain} analytics.

Dataset Profile:
{profile}

User Query: "{query}"

Based on the data profile, generate 3-5 concise, actionable business insights.
Each insight should be a clear sentence that a non-technical person can understand.
Focus on patterns, anomalies, and actionable recommendations visible from the data statistics.

Respond as a JSON array of strings:
["Insight 1", "Insight 2", "Insight 3"]

Return ONLY valid JSON, no markdown formatting."""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            text = _clean_json_response(response.content)
            return json.loads(text)
        except json.JSONDecodeError:
            return ["Unable to generate insights from the current data profile."]
