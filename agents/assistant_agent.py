import json
from utils.gemini_helper import call_gemini

class AssistantAgent:
    """
    AI Study Assistant Agent.
    Acts as a conversational tutor, answering student questions, explaining topics, 
    and generating mock viva questions using the student's personalized study context.
    """
    def __init__(self):
        self.system_instruction = (
            "You are a highly intelligent, encouraging AI Study Assistant. "
            "You are helping a student prepare for their exams based on their personalized study plan. "
            "Use the provided context (syllabus, progress, weak topics, uploaded PDFs, etc.) "
            "to give tailored, accurate, and structured answers. "
            "When explaining concepts, be clear and use examples if requested. "
            "Format your responses nicely in markdown."
        )

    def generate_response(self, user_query, chat_history, context_data):
        """
        Public method to generate a conversational response.
        Routes the request through the official MCP Server if available,
        otherwise falls back to the local _generate_response_local execution.
        """
        import json
        from utils.mcp_client import execute_mcp_tool
        
        args = {
            "prompt": user_query,
            "chat_history_json": json.dumps(chat_history) if chat_history else "[]",
            "context_data_json": json.dumps(context_data) if context_data else "{}"
        }
        
        res = execute_mcp_tool("explain_topic", args)
        if res.get("status") == "success":
            data = res.get("data")
            data["_source"] = "mcp"
            return data
            
        print(f"[MCP Fallback] explain_topic failed: {res.get('message')}. Using local fallback.")
        data = self._generate_response_local(user_query, chat_history, context_data)
        data["_source"] = "local"
        return data

    def _generate_response_local(self, user_query: str, chat_history: list, context_data: dict) -> dict:
        """
        Generates a conversational response based on the student's prompt and context.
        """
        
        # Build the context string
        context_str = "=== STUDENT CONTEXT ===\n"
        context_str += f"Subject: {context_data.get('subject', 'Unknown')}\n"
        context_str += f"Overall Progress: {context_data.get('progress_pct', 0)}%\n"
        context_str += f"Completed Topics: {', '.join(context_data.get('completed_topics', []))}\n"
        context_str += f"Weak Topics (from quizzes): {', '.join(context_data.get('weak_topics', []))}\n"
        
        syllabus_units = context_data.get("syllabus_units", [])
        if syllabus_units:
            context_str += "\n--- Syllabus ---\n"
            for u in syllabus_units:
                context_str += f"{u.get('unit_name', 'Unit')}: {', '.join(u.get('topics', []))}\n"
                
        study_plan = context_data.get("study_plan", [])
        if study_plan:
            context_str += "\n--- Current Study Plan ---\n"
            for day in study_plan[:5]: # just the next 5 days to avoid overloading context
                context_str += f"Day {day.get('day')}: {day.get('task')} ({day.get('hours')} hrs)\n"
                
        raw_text = context_data.get("raw_text", "")
        if raw_text:
            context_str += "\n--- PDF Excerpts ---\n"
            # Send up to 4000 chars of raw text to provide grounding without hitting token limits
            context_str += raw_text[:4000] + "\n"

        context_str += "\n=== CONVERSATION HISTORY ===\n"
        for msg in chat_history[-10:]: # last 10 messages
            role = "Student" if msg["role"] == "user" else "Assistant"
            context_str += f"{role}: {msg['content']}\n\n"
            
        # Combine everything into the final prompt
        final_prompt = (
            f"{context_str}\n"
            f"=== NEW QUERY ===\n"
            f"Student: {user_query}\n\n"
            f"Assistant:"
        )

        try:
            response_text = call_gemini(
                prompt=final_prompt,
                system_instruction=self.system_instruction,
                raise_exceptions=True
            )
            quota_exceeded = False
            error_msg = None
            reasoning = (
                f"Used {len(syllabus_units)} syllabus units, "
                f"progress ({context_data.get('progress_pct', 0)}%), "
                f"and {len(chat_history)} prior messages as context."
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                from utils.gemini_helper import get_mock_response
                response_text = get_mock_response(final_prompt)
                quota_exceeded = True
                error_msg = None
                reasoning = "Gemini API quota exceeded (429). Used offline mock."
            else:
                return {
                    "success": False,
                    "error": err_str
                }
                
        is_mock = "**[Mock AI Assistant]**" in response_text
        
        return {
            "success": True,
            "response": response_text,
            "reasoning": reasoning,
            "is_mock": is_mock,
            "quota_exceeded": quota_exceeded
        }
