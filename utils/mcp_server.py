from mcp.server.fastmcp import FastMCP
import json
import os
import sys
from datetime import datetime
import traceback

# Add project root to sys.path so it can import agents
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("StudyPlannerMCP")

def log_mcp_call(tool_name, args, status, response=None, error=None):
    """
    Logs an MCP tool execution to the central history JSON file.
    Used for monitoring and the Developer Panel.
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name,
        "args": args,
        "status": status,
        "response": response,
        "error": error
    }
    # Assume data directory is at project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(base_dir, "data", "mcp_history.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    history = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(log_entry)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

@mcp.tool()
def generate_study_plan(exam_date_str: str, syllabus_units_json: str, study_hours_per_day: int, selected_unit_names_json: str) -> str:
    """
    MCP Tool: Generates a day-by-day study plan.
    Delegates to PlannerAgent's local implementation.
    """
    try:
        from agents.planner_agent import StudyPlannerAgent
        syllabus_units = json.loads(syllabus_units_json)
        selected_unit_names = json.loads(selected_unit_names_json) if selected_unit_names_json else None
        res = StudyPlannerAgent()._generate_plan_local(exam_date_str, syllabus_units, study_hours_per_day, selected_unit_names)
        log_mcp_call("generate_study_plan", {"exam_date_str": exam_date_str, "study_hours": study_hours_per_day}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("generate_study_plan", {}, "error", error=str(e))
        raise e

@mcp.tool()
def generate_quiz(target_scope: str, num_questions: int, difficulty: str, topics_json: str) -> str:
    """
    MCP Tool: Generates an educational quiz for the specified scope.
    Delegates to QuizAgent's local implementation.
    """
    try:
        from agents.quiz_agent import QuizAgent
        topics = json.loads(topics_json) if topics_json else None
        res = QuizAgent()._generate_quiz_local(target_scope, num_questions, difficulty, topics)
        log_mcp_call("generate_quiz", {"target_scope": target_scope, "num_questions": num_questions, "difficulty": difficulty}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("generate_quiz", {"target_scope": target_scope}, "error", error=str(e))
        raise e

@mcp.tool()
def generate_ai_notes(target_scope: str, note_type: str, syllabus_units_json: str, topics_json: str = "[]") -> str:
    """
    MCP Tool: Generates structured study notes for a specific topic or scope.
    Delegates to NotesAgent's local implementation.
    """
    try:
        from agents.notes_agent import NotesAgent
        topics = json.loads(topics_json) if topics_json else None
        res = NotesAgent()._generate_notes_local(target_scope, note_type, syllabus_units_json, topics=topics)
        log_mcp_call("generate_ai_notes", {"target_scope": target_scope, "note_type": note_type}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("generate_ai_notes", {"target_scope": target_scope}, "error", error=str(e))
        raise e

@mcp.tool()
def generate_recommendations(exam_date_str: str, syllabus_units_json: str, completed_topics_json: str, study_hours_per_day: int) -> str:
    """
    MCP Tool: Generates strategic study recommendations based on progress and remaining time.
    Delegates to RecommendationAgent's local implementation.
    """
    try:
        from agents.recommendation_agent import RecommendationAgent
        syllabus_units = json.loads(syllabus_units_json)
        completed_topics = json.loads(completed_topics_json)
        res = RecommendationAgent()._generate_recommendations_local(exam_date_str, syllabus_units, completed_topics, study_hours_per_day)
        log_mcp_call("generate_recommendations", {"exam_date_str": exam_date_str}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("generate_recommendations", {}, "error", error=str(e))
        raise e

@mcp.tool()
def explain_topic(prompt: str, chat_history_json: str, context_data_json: str) -> str:
    """
    MCP Tool: Answers a student's query interactively as an AI Study Assistant.
    Delegates to AssistantAgent's local implementation.
    """
    try:
        from agents.assistant_agent import AssistantAgent
        chat_history = json.loads(chat_history_json)
        context_data = json.loads(context_data_json)
        res = AssistantAgent()._generate_response_local(prompt, chat_history, context_data)
        log_mcp_call("explain_topic", {"prompt": prompt}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("explain_topic", {"prompt": prompt}, "error", error=str(e))
        raise e

@mcp.tool()
def search_syllabus(query: str, syllabus_units_json: str) -> str:
    """
    MCP Tool: Searches through the provided syllabus JSON for a specific topic.
    Returns standard JSON response.
    """
    try:
        syllabus = json.loads(syllabus_units_json)
        results = []
        q = query.lower()
        for unit in syllabus.get("units", []):
            if q in unit.get("unit_name", "").lower():
                results.append(unit.get("unit_name"))
            for topic in unit.get("topics", []):
                if q in topic.lower():
                    results.append(f"{unit.get('unit_name')} - {topic}")
        res = {"success": True, "results": results}
        log_mcp_call("search_syllabus", {"query": query}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("search_syllabus", {"query": query}, "error", error=str(e))
        raise e

@mcp.tool()
def view_progress(completed_topics_json: str, flat_topics_json: str) -> str:
    """
    MCP Tool: Calculates study progress percentage based on completed topics.
    Returns standard JSON response.
    """
    try:
        completed_topics = json.loads(completed_topics_json)
        flat_topics = json.loads(flat_topics_json)
        total = len(flat_topics)
        completed = len(completed_topics)
        pct = int((completed / total) * 100) if total > 0 else 0
        res = {"success": True, "completed": completed, "total": total, "percentage": pct}
        log_mcp_call("view_progress", {}, "success", response=res)
        return json.dumps(res)
    except Exception as e:
        log_mcp_call("view_progress", {}, "error", error=str(e))
        raise e

if __name__ == "__main__":
    mcp.run()
