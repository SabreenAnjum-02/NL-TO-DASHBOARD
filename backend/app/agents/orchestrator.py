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

    def __init__(self):
        self.llm = ChatOpenAI(temperature=0, model_name="anthropic/claude-3-haiku")
        
    async def _classify_intent(self, query: str, profile_text: str, context: str) -> str:
        prompt = "Classify user intent: 'chat' (general greeting) or 'analytical' (data query).\nQuery: " + query + "\nReply ONLY with 'chat' or 'analytical'."
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            text = response.content.strip().lower()
            if "chat" in text: return "chat"
            return "analytical"
        except Exception:
            return "analytical"
            
    async def _handle_chat(self, query: str, profile_text: str, context: str) -> str:
        prompt = "You are DataSense AI. User: " + query + "\nDataset Profile: " + profile_text + "\nReply cleanly in 1-2 sentences."
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception:
            return "Hello! How can I help you analyze your data today?"
            
    async def _detect_domain(self, profile_text: str) -> str:
        prompt = "Identify business domain for this dataset. Reply in 1-3 words.\nProfile: " + profile_text
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception:
            return "General"
            
    async def _generate_insights(self, query: str, results_text: str, domain: str) -> list:
        prompt = "Generate 2-3 bullet points of analytical insights for this query based EXACTLY on the actual returned data.\nQuery: " + query + "\nActual Data Result: " + results_text + "\nDo NOT invent values. Ground all insights in the actual data provided.\nReturn a JSON array of strings."
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            cleaned = response.content.strip()
            if cleaned.startswith("```json"): cleaned = cleaned[7:]
            elif cleaned.startswith("```"): cleaned = cleaned[3:]
            if cleaned.endswith("```"): cleaned = cleaned[:-3]
            return __import__("json").loads(cleaned.strip())
        except Exception:
            return ["Explore the generated charts for detailed insights."]

    async def _format_text_answer(self, query: str, results: list) -> str:
        results_text = str(results[:10])
        try:
            format_prompt = "User asked: " + query + "\nDatabase returned: " + results_text + "\nWrite a clear 1-2 sentence answer in plain English using these numbers. Do not mention database or query."
            response = self.llm.invoke([HumanMessage(content=format_prompt)])
            return response.content.strip()
        except Exception:
            return "The answer is: " + ", ".join([f"{k}: {v}" for k, v in results[0].items()])
            
    async def _decide_visualization(self, query: str, sql: str, results: list, profile_text: str) -> dict:
        if not results: return {"should_visualize": False}
        columns = list(results[0].keys())
        dtypes = {}
        for k in columns:
            val = results[0][k]
            if isinstance(val, (int, float)): dtypes[k] = "numeric"
            else: dtypes[k] = "categorical/temporal"
        prompt = "You are a Visualization Decision agent.\nDecide if the following SQL result should be visualized.\nUser Question: " + query + "\nSQL Query Executed: " + sql + "\nResult Columns: " + str(columns) + "\nData Types Sample: " + str(dtypes) + "\nNumber of Rows: " + str(len(results)) + "\n\nRules:\n1. Return JSON ONLY. No markdown.\n2. If the user asked for a single scalar value, a simple total, or a yes/no, set should_visualize to false.\n3. If visualization is useful, pick the most appropriate chart_type (bar, line, pie, arc).\\n4. Do NOT invent fields. x_field and y_field MUST exactly match one of the Result Columns.\n\nFormat:\n{\n  \"should_visualize\": true/false,\n  \"chart_type\": \"bar\",\n  \"x_field\": \"col_name\",\n  \"y_field\": \"col_name\",\n  \"title\": \"Chart Title\",\n  \"reason\": \"Why this chart makes sense\"\n}\n"
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            cleaned = response.content.strip()
            if cleaned.startswith("```json"): cleaned = cleaned[7:]
            elif cleaned.startswith("```"): cleaned = cleaned[3:]
            if cleaned.endswith("```"): cleaned = cleaned[:-3]
            return __import__("json").loads(cleaned.strip())
        except Exception:
            return {"should_visualize": False}
            
    def _generate_visualizations_from_decision(self, decision: dict, results: list) -> list:
        if not decision.get("should_visualize"): return []
        chart_type = decision.get("chart_type", "bar")
        x_field = decision.get("x_field")
        y_field = decision.get("y_field")
        if not x_field or not y_field: return []
        if x_field not in results[0] or y_field not in results[0]: return []
        
        # Filter nulls properly without failing on ints
        clean_results = []
        for r in results:
            val = r.get(x_field)
            if val is not None and str(val).strip() != "" and str(val).lower() != "null":
                clean_results.append(r)
                
        if not clean_results: return []

        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "mark": {"type": chart_type, "tooltip": True},
            "data": {"values": clean_results},
            "encoding": {
                "x": {"field": x_field, "type": "nominal" if chart_type == "bar" else "temporal"},
                "y": {"field": y_field, "type": "quantitative"}
            }
        }
        if chart_type == "bar":
            spec["encoding"]["x"]["sort"] = "-y"
        if chart_type in ["pie", "arc"]:
            spec = {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "mark": {"type": "arc", "tooltip": True},
                "data": {"values": clean_results},
                "encoding": {
                    "theta": {"field": y_field, "type": "quantitative"},
                    "color": {"field": x_field, "type": "nominal"}
                }
            }
        return [spec]
        
    async def _execute_query_with_retry(self, query: str, profile_text: str, dataset_id: str, context: str) -> dict:
        from main import data_service
        import json
        try:
            profile_dict = json.loads(profile_text)
            tables_dict = profile_dict.get("tables", {})
            max_table_rows = max([t.get("row_count", 0) for t in tables_dict.values()] + [0])
        except Exception:
            profile_dict = {}
            tables_dict = {}
            max_table_rows = 1000000

        sql_prompt = "You are a SQL generation agent. Generate a single DuckDB SQL SELECT query to answer the user's question.\nDataset profile:\n" + profile_text + "\nQuestion: " + query + "\nRules:\n- Return ONLY valid DuckDB SQL query. No markdown.\n- Use explicit table names (e.g. FROM \"dataset_xyz_Vendors\"). Do NOT use {{table}}.\n- MUST wrap column names and table names in double quotes.\n- Do NOT join tables unnecessarily.\n- Respect table grain to avoid double-counting.\nSQL:"
        sql = ""
        results = None
        error_msg = ""
        for attempt in range(3):
            try:
                if attempt == 0:
                    sql_response = self.llm.invoke([HumanMessage(content=sql_prompt)])
                else:
                    retry_prompt = sql_prompt + "\n\nPREVIOUS ATTEMPT FAILED\nSQL:\n" + sql + "\nError:\n" + error_msg + "\nFix the SQL query."
                    sql_response = self.llm.invoke([HumanMessage(content=retry_prompt)])
            except Exception as provider_err:
                err_str = str(provider_err).lower()
                if "402" in err_str or "payment" in err_str or "quota" in err_str or "credits" in err_str:
                    return {"error": "AI service limit reached. Please try again later."}
                elif "429" in err_str or "rate limit" in err_str:
                    return {"error": "AI service rate limit reached. Please try again in a moment."}
                elif "500" in err_str or "502" in err_str or "503" in err_str or "service unavailable" in err_str:
                    return {"error": "AI service is temporarily unavailable. Please try again later."}
                elif "timeout" in err_str or "connection" in err_str:
                    return {"error": "AI service connection timed out. Please try again."}
                else:
                    return {"error": "AI service is temporarily unavailable. Please try again later."}
            
            sql = sql_response.content.strip()
            if sql.startswith("```sql"): sql = sql[6:]
            elif sql.startswith("```"): sql = sql[3:]
            if sql.endswith("```"): sql = sql[:-3]
            sql = sql.strip()
            
            try:
                used_tables = [t for t in tables_dict.keys() if '"' + t + '"' in sql or t in sql]
                grains = [tables_dict[t].get("grain", "") for t in used_tables]
                has_agg = any("aggregated" in g.lower() or "summary" in g.lower() for g in grains)
                has_detail = any("detail" in g.lower() or "transaction" in g.lower() or "time-series" in g.lower() or "entity-level" in g.lower() for g in grains)
                
                if has_agg and has_detail and "JOIN" in sql.upper():
                     raise ValueError("Validation Error: The query attempts to JOIN a transaction-level table with a pre-aggregated summary table. This causes double-counting of overlapping monetary information.")
                
                results = data_service.execute_query(dataset_id, sql)
                
                if not results:
                    raise ValueError("The query executed successfully but returned 0 rows. DIAGNOSTIC: Check if filters are too restrictive.")
                    
                if "JOIN" in sql.upper():
                    if len(results) > (max_table_rows * 2) and max_table_rows > 0:
                        raise ValueError("Suspicious JOIN multiplication: The query returned suspiciously many rows. You may have created a many-to-many cross join.")
                
                return {"results": results, "sql": sql}
            except Exception as e:
                error_msg = str(e)
                results = None
                
        if "0 rows" in error_msg:
            return {"error": "The requested information could not be found in the uploaded data or the query returned no results."}
        return {"error": "I tried to analyze the data but could not generate a valid query. Please rephrase your question."}
        
    async def process_query(self, query: str, dataset_id: str, context: Optional[str] = None) -> dict:
        try:
            from main import data_service
            import json
            context_str = context or ""
            profile_text = ""
            profile = {}
            try:
                dataset_info = data_service.get_summary(dataset_id)
                profile = dataset_info["profile"]
                profile_text = json.dumps(profile, indent=2, default=str)
            except Exception as e:
                if "session_expired" in str(e): raise e
                pass

            if not profile_text:
                return {"status": "error", "message": f"Dataset '{dataset_id}' not found. Please upload data first."}

            intent = await self._classify_intent(query, profile_text, context_str)
            if intent == "chat":
                chat_response = await self._handle_chat(query, profile_text, context_str)
                return {"status": "chat_reply", "message": chat_response}

            sql_exec = await self._execute_query_with_retry(query, profile_text, dataset_id, context_str)
            if sql_exec.get("error"):
                return {"status": "error", "message": sql_exec["error"]}
                
            results = sql_exec.get("results")
            sql = sql_exec.get("sql")
            results_text = str(results[:10])

            vis_decision = await self._decide_visualization(query, sql, results, profile_text)
            
            if not vis_decision.get("should_visualize"):
                text_resp = await self._format_text_answer(query, results)
                return {"status": "text_answer", "message": text_resp}

            domain = await self._detect_domain(profile_text)
            vega_specs = self._generate_visualizations_from_decision(vis_decision, results)
            
            if not vega_specs:
                text_resp = await self._format_text_answer(query, results)
                return {"status": "text_answer", "message": text_resp}

            insights = await self._generate_insights(query, results_text, domain)

            dashboardData = []
            for spec in vega_specs:
                dashboardData.append({
                    "title": vis_decision.get("title", "Visualization"),
                    "description": vis_decision.get("reason", ""),
                    "vega_lite_spec": spec
                })

            return {
                "status": "dashboard",
                "dashboardData": dashboardData,
                "insights": insights
            }
        except Exception as e:
            return {"status": "error", "message": "An unexpected error occurred: " + str(e)}
