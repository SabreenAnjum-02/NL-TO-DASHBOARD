import os
import json
import re
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def _clean_json_response(text: str) -> str:
    """Extract valid JSON from LLM responses, stripping markdown fences and extra text."""
    text = text.strip()

    # Remove markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try to find JSON array or object boundaries
    start_arr = text.find('[')
    start_obj = text.find('{')

    if start_arr == -1 and start_obj == -1:
        return text

    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        end = text.rfind(']')
        if end != -1:
            return text[start_arr:end + 1]
    elif start_obj != -1:
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
        """
        try:
            from main import data_service
            
            context_str = context or ""

            # Step 0a: Get dataset profile
            profile_text = ""
            profile = {}
            try:
                dataset_info = data_service.get_summary(dataset_id)
                profile = dataset_info["profile"]
                profile_text = json.dumps(profile, indent=2, default=str)
            except Exception as e:
                if "session_expired" in str(e):
                    raise e # Let the router handle session_expired specially
                pass

            # Step 0b: Intent Classification
            intent = await self._classify_intent(query, profile_text, context_str)
            if intent == "chat":
                chat_response = await self._handle_chat(query, profile_text, context_str)
                return {
                    "status": "chat_reply",
                    "message": chat_response,
                }

            if not profile_text:
                return {
                    "status": "error",
                    "message": f"Dataset '{dataset_id}' not found. Please upload data first.",
                }

            # Step 0c: Output Type Decision
            output_type = await self._decide_output_type(query, profile_text)
            
            if output_type == "text_answer":
                text_resp = await self._execute_and_format_query(query, profile_text, dataset_id, context_str, format_as="text")
                return {
                    "status": "text_answer",
                    "message": text_resp,
                }
            elif output_type == "table":
                table_resp = await self._execute_and_format_query(query, profile_text, dataset_id, context_str, format_as="table")
                return {
                    "status": "table_answer",
                    "message": table_resp,
                }

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

            # Step 3: Task Planning
            task_plan = await self._plan_tasks(query, profile_text, domain)

            # Step 4: Visual Generation
            vega_specs = await self._generate_visualizations(
                query, profile_text, domain, task_plan, context_str
            )

            # Step 4.5: Validate Analytical Correctness
            validated_specs = await self._validate_analytical_correctness(query, vega_specs, profile_text)

            # Step 5: Self-Correction
            corrected_specs = await self._self_correct(validated_specs, profile)
            
            # Safe fallback if charts failed
            if not corrected_specs and output_type in ["chart", "dashboard"]:
                 text_resp = await self._execute_and_format_query(query, profile_text, dataset_id, context_str, format_as="text")
                 return {
                     "status": "text_answer",
                     "message": "I couldn't generate a reliable chart for this, but here is the data: " + text_resp,
                 }

            # Step 6: Generate insights
            insights = await self._generate_insights(query, profile_text, domain)

            return {
                "status": "success",
                "domain": domain,
                "task_plan": task_plan,
                "charts": corrected_specs,
                "insights": insights,
                "query": query,
            }
        except Exception as e:
            error_str = str(e)
            if "session_expired" in error_str:
                raise e
            if "402" in error_str or "credits" in error_str.lower():
                return {
                    "status": "text_answer",
                    "message": "⚠️ **API Limit Reached:** Your OpenRouter API account has run out of credits or hit a rate limit. Please add credits at [openrouter.ai/settings/credits](https://openrouter.ai/settings/credits) to continue generating insights and dashboards.",
                }
            return {
                "status": "text_answer",
                "message": f"I'm sorry, I encountered an unexpected error while analyzing your request: {error_str}",
            }

    async def _classify_intent(self, query: str, profile_text: str = "", context: str = "") -> str:
        lowered = query.lower().strip()
        chat_shortcuts = ["hello", "hi", "hey", "who are you", "help", "what can you do"]
        if any(lowered == word or lowered.startswith(word + " ") for word in chat_shortcuts):
            return "chat"

        prompt = f"""Classify the following user message as either 'chat' or 'data'.

- 'chat': Greetings, casual conversation, questions about what you can do, or general help.
- 'data': Any question asking to analyze, summarize, visualize, or query the uploaded dataset.

Recent conversation context:
{context}

Dataset Profile:
{profile_text}

User message: "{query}"

Respond with ONLY the word 'chat' or 'data'.
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = response.content.strip().lower()
            return "data" if "data" in result else "chat"
        except Exception:
            return "data"

    async def _handle_chat(self, query: str, profile_text: str = "", context: str = "") -> str:
        prompt = f"""You are InsightFlow, an AI data analyst.
        
Recent conversation context:
{context}

Dataset profile (if available):
{profile_text}

Respond conversationally to the user's message: "{query}"
Keep it brief and helpful. If they have data uploaded, remind them they can ask you to analyze it or create charts.
"""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()

    async def _decide_output_type(self, query: str, profile_text: str) -> str:
        lowered = query.lower()
        explicit_chart = ["plot", "chart", "graph", "visualize", "visualise", "draw", "bar chart", "line chart", "pie chart", "scatter"]
        if any(w in lowered for w in explicit_chart):
            return "chart"
        if "dashboard" in lowered:
            return "dashboard"
            
        prompt = f"""You are an output-type decision agent.
Dataset Profile:
{profile_text}

User Query: "{query}"

Decide the most appropriate output type based on the COMPLETE SEMANTIC MEANING of this question.

Options:
- "text_answer": A single, complete answer expressible as 1-2 sentences. 
  (e.g., "How many rows?", "Total revenue?", "Which region has highest sales?")
- "table": A list of items with multiple attributes.
  (e.g., "List all products and prices", "Top 5 customers with their details")
- "chart": A breakdown, comparison across categories, trend over time, distribution, or ranking that requires visual representation.
  (e.g., "How did sales change monthly?", "Compare sales by region", "What is the monthly average?", "Top 10 products by revenue")
- "dashboard": A broad overview or multiple metrics at once.

IMPORTANT: When uncertain, do NOT generate a chart unless there is evidence that visualization is required. Text or table is preferred for ambiguous queries.
Respond with ONLY one word: text_answer | table | chart | dashboard
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result = response.content.strip().lower()
            if "dashboard" in result: return "dashboard"
            if "table" in result: return "table"
            if "chart" in result: return "chart"
            return "text_answer"
        except Exception:
            return "text_answer" # Safe fallback

    async def _execute_and_format_query(self, query: str, profile_text: str, dataset_id: str, context: str, format_as: str) -> str:
        from main import data_service
        sql_prompt = f"""You are a SQL generation agent. Generate a single DuckDB SQL SELECT query to answer the user's question.

Dataset profile (includes column names, types, samples, etc):
{profile_text}

User question: "{query}"
Recent context:
{context}

Rules:
- Return ONLY the SQL query, no markdown fences, no explanation.
- Use "{{{{table}}}}" as the exact table name placeholder.
- ALWAYS wrap column names in double quotes (e.g. "Total Revenue").
- Limit results to 20 rows maximum.
- CRITICAL: If you need to cast a string column to a number for sorting or aggregation, ALWAYS use TRY_CAST("col" AS DOUBLE) instead of CAST(), so it safely ignores text values.
- CRITICAL: If your query groups by or selects a categorical entity (like "Client Name"), you MUST add `WHERE "Col" IS NOT NULL` to prevent returning blank or 'None' rows.
- CRITICAL: This table concatenates multiple Excel sheets. The "Sheet_Name" column tells you which sheet a row came from. When querying a specific column, look at its 'valid_sheets' property in the profile, and ALWAYS filter your query using WHERE "Sheet_Name" = '...' to pick the correct sheet! If you don't filter, you will get NULLs or double-counted data.

SQL:"""
        sql = ""
        results = None
        error_msg = ""
        
        # Self-healing retry loop for SQL execution
        for attempt in range(2):
            try:
                if attempt == 0:
                    sql_response = self.llm.invoke([HumanMessage(content=sql_prompt)])
                else:
                    retry_prompt = sql_prompt + f"\n\nYour previous SQL query failed with this error: {error_msg}\nPlease fix the SQL query and try again. Ensure column names are exactly as they appear in the profile and wrap them in double quotes. Return ONLY the fixed SQL query."
                    sql_response = self.llm.invoke([HumanMessage(content=retry_prompt)])
                    
                sql = sql_response.content.strip().strip("```sql").strip("```").strip()
                results = data_service.execute_query(dataset_id, sql)
                break  # Success!
            except Exception as e:
                error_msg = str(e)
                if "402" in error_msg or "credits" in error_msg.lower():
                    return "⚠️ **API Limit Reached:** Your OpenRouter API account has run out of credits or hit a rate limit. Please add credits at openrouter.ai/settings/credits."
                
        if results is None:
            return f"I tried to analyze the data but ran into a calculation error. Could you rephrase your question? (Internal error: {error_msg})"

        try:
            if not results:
                return "The query returned no data."

            if format_as == "table":
                # Render markdown table manually since it's reliable
                keys = list(results[0].keys())
                header = "| " + " | ".join(keys) + " |"
                sep = "|" + "|".join(["---"] * len(keys)) + "|"
                rows = []
                for row in results:
                    rows.append("| " + " | ".join(str(row[k]) for k in keys) + " |")
                return "\n".join([header, sep] + rows)
            else:
                results_text = str(results[:10])
                format_prompt = f"""The user asked: "{query}"
The database returned: {results_text}
Write a clear, concise 1-2 sentence answer in plain English using these exact numbers. Do not mention the database or query.
CRITICAL: If dealing with money, use the appropriate currency symbol (e.g., ₹ if the dataset appears to be Indian or default to ₹) or format the number exactly as it appears. Do NOT default to USD ($)."""
                format_response = self.llm.invoke([HumanMessage(content=format_prompt)])
                return format_response.content.strip()
        except Exception as e:
            return f"I generated the data but couldn't format it properly. Error: {str(e)}"

    async def _detect_ambiguity(self, query: str, profile_text: str) -> dict:
        prompt = f"""Analyze this query against the dataset profile to determine if it is TOO ambiguous to process.
Dataset Profile: {profile_text}
Query: "{query}"
Only flag as ambiguous if a critical column reference is completely unknown. Be lenient.
Return JSON format: {{"is_ambiguous": boolean, "questions": ["Clarification 1", ...]}}
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            result_json = json.loads(_clean_json_response(response.content))
            return result_json
        except Exception:
            return {"is_ambiguous": False, "questions": []}

    async def _detect_domain(self, profile_text: str) -> str:
        prompt = f"""Given this dataset profile, identify the business domain (e.g., Sales, HR, Finance).
Profile: {profile_text}
Return ONLY a 1-3 word domain name."""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()

    async def _plan_tasks(self, query: str, profile_text: str, domain: str) -> dict:
        prompt = f"""Create a DAG task plan for generating a dashboard to answer: "{query}"
Domain: {domain}
Profile: {profile_text}
Return JSON: {{"tasks": [{{"id": "t1", "type": "chart", "description": "...", "dependencies": []}}]}}
Keep it to 1-3 highly relevant charts."""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return json.loads(_clean_json_response(response.content))
        except Exception:
            return {"tasks": []}

    async def _generate_visualizations(self, query: str, profile_text: str, domain: str, task_plan: dict, context: str) -> list:
        prompt = f"""Generate Vega-Lite specifications based on this task plan.
Query: "{query}"
Context: {context}
Profile: {profile_text}
Plan: {json.dumps(task_plan, indent=2)}

Rules for Vega-Lite:
1. Return a JSON array of objects: [{{"id": "t1", "vega_lite_spec": {{"$schema": "...", "mark": "...", ...}}}}]
2. DO NOT include "data" with "values". Use "data": {{"name": "dataset"}} as a placeholder.
3. Use exact column names from the profile.
4. For rankings / Top-N, ALWAYS use a transform with window/rank and filter. Use a horizontal bar chart (`"mark": "bar"`, y-axis = category, x-axis = value).
5. For time series, use `"mark": "line"`.
6. CRITICAL: Your dataset contains concatenated sheets. You MUST filter out null values for the primary fields you are visualizing using a transform (e.g., `{{"filter": "datum['Client Name'] != null"}}`). Otherwise, 'null' will dominate the charts!

Return valid JSON array."""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            specs = json.loads(_clean_json_response(response.content))
            if not isinstance(specs, list):
                specs = [specs]
            return specs
        except Exception as e:
            return []

    async def _validate_analytical_correctness(self, query: str, vega_specs: list, profile_text: str) -> list:
        """Validates that the aggregation/grouping in the Vega spec matches the semantic intent of the query."""
        if not vega_specs:
            return vega_specs

        prompt = f"""You are a strict data analysis validator. 
Review the following Vega-Lite specifications to ensure the analytical operations (aggregations, groupings, filters) perfectly match the user's semantic intent.

User Query: "{query}"
Dataset Profile: {profile_text}

Vega-Lite Specs:
{json.dumps(vega_specs, indent=2)}

Checklist:
1. Did the user ask for an average but the spec uses "sum" (or vice-versa)?
2. Is the time-grouping correct (e.g. month vs year)?
3. Is a ranking request (e.g. "top 10") actually sorting and limiting?
4. Are the axes mapped to the correct data types?

If any spec has incorrect analytical operations, FIX the JSON specification so it calculates the right answer.
Return the corrected JSON array of specifications exactly as provided (with your fixes). DO NOT return anything except the JSON array.
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            corrected = json.loads(_clean_json_response(response.content))
            if isinstance(corrected, list):
                return corrected
            return vega_specs
        except Exception:
            return vega_specs

    async def _self_correct(self, vega_specs: list, profile: dict) -> list:
        cols = profile.get("columns", [])
        valid_columns = set()
        for col in cols:
            if isinstance(col, dict):
                valid_columns.add(col["name"])
            else:
                valid_columns.add(str(col))

        corrected = []
        for spec_obj in vega_specs:
            spec = spec_obj.get("vega_lite_spec", {})
            if not spec:
                continue
                
            if "$schema" not in spec:
                spec["$schema"] = "https://vega.github.io/schema/vega-lite/v5.json"
            if "width" not in spec:
                spec["width"] = "container"
            if "height" not in spec:
                spec["height"] = 300

            # Programmatically guarantee NO null values in charts
            if "transform" not in spec:
                spec["transform"] = []
                
            fields_to_filter = set()
            for channel, enc in spec.get("encoding", {}).items():
                if isinstance(enc, dict) and "field" in enc:
                    fields_to_filter.add(enc["field"])
                    
            for field in fields_to_filter:
                filter_expr = f"isValid(datum['{field}']) && datum['{field}'] != null && datum['{field}'] != 'null' && datum['{field}'] != 'None' && datum['{field}'] != 'NaN'"
                spec["transform"].append({"filter": filter_expr})

            # Column Name Validation
            if valid_columns:
                bad_fields = self._find_bad_fields(spec, valid_columns)
                if bad_fields:
                    continue # Drop spec with invalid columns

            spec_obj["vega_lite_spec"] = spec
            corrected.append(spec_obj)
            
        return corrected

    def _find_bad_fields(self, spec: dict, valid_columns: set) -> list:
        valid_local = set(valid_columns)
        # First pass: collect derived fields created by Vega-Lite transforms
        for transform in spec.get("transform", []):
            if isinstance(transform, dict):
                for agg in transform.get("aggregate", []):
                    if isinstance(agg, dict) and "as" in agg:
                        valid_local.add(agg["as"])
                if "calculate" in transform and "as" in transform:
                    valid_local.add(transform["as"])

        bad = []
        encoding = spec.get("encoding", {})
        for channel, enc in encoding.items():
            if isinstance(enc, dict) and "field" in enc:
                if enc["field"] not in valid_local:
                    bad.append(enc["field"])
        for transform in spec.get("transform", []):
            if isinstance(transform, dict):
                for agg in transform.get("aggregate", []):
                    if isinstance(agg, dict) and "field" in agg and agg["field"] not in valid_local:
                        bad.append(agg["field"])
                if "groupby" in transform:
                    grp = transform["groupby"]
                    if isinstance(grp, list):
                        for g in grp:
                            if g not in valid_local: bad.append(g)
                    elif isinstance(grp, str):
                        if grp not in valid_local: bad.append(grp)
        return bad

    async def _generate_insights(self, query: str, profile_text: str, domain: str) -> list:
        prompt = f"""Generate 3-4 bullet points of analytical insights or follow-up questions for this query.
Query: "{query}"
Profile: {profile_text}
Return a JSON array of strings."""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return json.loads(_clean_json_response(response.content))
        except Exception:
            return ["Explore the generated charts for detailed insights."]
