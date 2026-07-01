import json
from datetime import datetime, date
from utils.gemini_helper import call_gemini

class RecommendationAgent:
    """
    Recommendation Engine Agent.
    Analyzes the student's exam timeline, syllabus, and completed topics 
    to provide smart, prioritized study recommendations and strategies.
    """
    def __init__(self):
        pass

    def generate_recommendations(self, exam_date_str, syllabus_units, completed_topics, study_hours_per_day):
        """
        Public method to generate study recommendations.
        Routes the request through the official MCP Server if available,
        otherwise falls back to the local _generate_recommendations_local execution.
        """
        import json
        from utils.mcp_client import execute_mcp_tool
        
        args = {
            "exam_date_str": str(exam_date_str) if exam_date_str else "",
            "syllabus_units_json": json.dumps(syllabus_units) if syllabus_units else "[]",
            "completed_topics_json": json.dumps(completed_topics) if completed_topics else "[]",
            "study_hours_per_day": study_hours_per_day
        }
        
        res = execute_mcp_tool("generate_recommendations", args)
        if res.get("status") == "success":
            data = res.get("data")
            data["_source"] = "mcp"
            return data
            
        print(f"[MCP Fallback] generate_recommendations failed: {res.get('message')}. Using local fallback.")
        data = self._generate_recommendations_local(exam_date_str, syllabus_units, completed_topics, study_hours_per_day)
        data["_source"] = "local"
        return data

    def _generate_recommendations_local(self, exam_date_str, syllabus_units, completed_topics, study_hours_per_day):
        """
        Analyzes the student's progress and generates personalized AI recommendations.
        """
        # Flatten all syllabus topics
        flat_topics = []
        for unit in syllabus_units:
            unit_name = unit.get("unit_name", "Unit")
            for topic in unit.get("topics", []):
                flat_topics.append(f"{unit_name} - {topic}")
                
        remaining_topics = [t for t in flat_topics if t not in completed_topics]
        
        # Calculate days remaining
        days_remaining = -1
        try:
            if isinstance(exam_date_str, str) and exam_date_str:
                exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
                days_remaining = (exam_date - date.today()).days
        except Exception as e:
            print(f"Error parsing date in recommendation agent: {e}")
            
        prompt = f"""
        You are a highly supportive AI Study Advisor. Based on the student's study context below, generate strategic study recommendations.
        
        Student Context:
        - Days remaining until exam: {days_remaining}
        - Total topics/units: {len(flat_topics)}
        - Completed topics: {completed_topics}
        - Remaining topics to learn: {remaining_topics}
        - Study hours available per day: {study_hours_per_day}
        
        You must return a raw JSON object. Do not wrap the JSON output in markdown formatting.
        The JSON structure MUST follow this schema:
        {{
          "reasoning": "A detailed explanation of why these recommendations were selected, citing the remaining days and topics.",
          "recommendations": [
            {{
              "text": "Specific recommendation action item.",
              "priority": "High"  // High, Medium, or Low
            }}
          ]
        }}
        """
        
        system_instruction = "You are a study recommendation agent that outputs personalized recommendations in valid JSON format only."
        
        try:
            response_text = call_gemini(prompt, system_instruction=system_instruction, response_mime_type="application/json")
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            
            rec_data = json.loads(clean_text)
            return {
                "success": True,
                "reasoning": rec_data.get("reasoning", "No reasoning provided."),
                "recommendations": rec_data.get("recommendations", [])
            }
        except Exception as e:
            print(f"Error parsing recommendations: {e}")
            fallback_recs = []
            
            if days_remaining > 0:
                if remaining_topics:
                    next_topic = remaining_topics[0]
                    fallback_recs.append({
                        "text": f"Focus on understanding the core concepts of '{next_topic}' tomorrow.",
                        "priority": "High"
                    })
                
                if completed_topics:
                    rev_topic = completed_topics[-1]
                    fallback_recs.append({
                        "text": f"Spend 20-30 minutes revising '{rev_topic}' to maintain retention.",
                        "priority": "Medium"
                    })
                
                if days_remaining <= 5:
                    fallback_recs.append({
                        "text": "The exam is very close! Take a full mock test under timed conditions to practice speed.",
                        "priority": "High"
                    })
                else:
                    fallback_recs.append({
                        "text": "Maintain your steady daily schedule. Take short breaks during your study sessions.",
                        "priority": "Low"
                    })
            else:
                fallback_recs.append({
                    "text": "Set up your student profile and exam details to get personalized recommendations.",
                    "priority": "Medium"
                })

            return {
                "success": True,
                "reasoning": "Fell back to rule-based logic because Gemini API response could not be parsed.",
                "recommendations": fallback_recs
            }

