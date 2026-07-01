import math
from datetime import datetime, date

class StudyPlannerAgent:
    """
    Study Planner Agent.
    Responsible for generating dynamic, day-by-day study schedules 
    based on the student's exam date, syllabus units, and study hours.
    """
    def __init__(self):
        pass

    def generate_plan(self, exam_date_str, syllabus_units, study_hours_per_day, selected_unit_names=None):
        """
        Public method to generate a study plan.
        Routes the request through the official MCP Server if available,
        otherwise falls back to the local _generate_plan_local execution.
        """
        import json
        from utils.mcp_client import execute_mcp_tool

        args = {
            "exam_date_str": str(exam_date_str),
            "syllabus_units_json": json.dumps(syllabus_units),
            "study_hours_per_day": study_hours_per_day,
            "selected_unit_names_json": json.dumps(selected_unit_names) if selected_unit_names else ""
        }

        try:
            res = execute_mcp_tool("generate_study_plan", args)

            if res.get("status") == "success":
                data = res.get("data")
                data["_source"] = "mcp"
                return data

            print(f"[MCP Fallback] generate_study_plan failed: {res.get('message')}")

        except Exception as e:
            print(f"[MCP ERROR] {e}")

        data = self._generate_plan_local(
            exam_date_str,
            syllabus_units,
            study_hours_per_day,
            selected_unit_names
        )
        data["_source"] = "local"
        return data

    def _generate_plan_local(self, exam_date_str, syllabus_units, study_hours_per_day, selected_unit_names=None):
        """
        Generates a structured day-by-day study plan.
        """

        reasoning_steps = []
        plan_days = []

        
        # 1. Parse Exam Date and calculate remaining days
        try:
            if isinstance(exam_date_str, str):
                exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
            else:
                exam_date = exam_date_str
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid date format: {e}",
                "reasoning": ["Failed to parse exam date."],
                "plan": []
            }
            
        today = date.today()
        days_remaining = (exam_date - today).days
        
        reasoning_steps.append(f"Exam date configuration: {exam_date}. Current date: {today}.")
        reasoning_steps.append(f"Total days remaining: {days_remaining} day(s).")
        
        if days_remaining <= 0:
            reasoning_steps.append("ERROR: Selected exam date is in the past or is today. Cannot schedule future study days.")
            return {
                "success": False,
                "error": "Exam date must be in the future.",
                "reasoning": reasoning_steps,
                "plan": []
            }

        # 2. Filter units & build list of topics
        filtered_units = []
        if selected_unit_names:
            filtered_units = [u for u in syllabus_units if u["unit_name"] in selected_unit_names]
            reasoning_steps.append(f"Filter scope: Selected {len(filtered_units)} of {len(syllabus_units)} units.")
        else:
            filtered_units = syllabus_units
            reasoning_steps.append(f"Filter scope: Planning for entire syllabus ({len(syllabus_units)} units).")
            
        # Build flattened topic list: "Unit Name - Topic Title"
        flat_topics = []
        for unit in filtered_units:
            unit_name = unit.get("unit_name", "Unit")
            for topic in unit.get("topics", []):
                flat_topics.append(f"{unit_name}: {topic}")
                
        if not flat_topics:
            reasoning_steps.append("WARNING: No topics found in the selected scope. Using general units template.")
            flat_topics = [f"Unit {i+1} core study" for i in range(5)]
            
        num_topics = len(flat_topics)
        reasoning_steps.append(f"Identified {num_topics} topic items across selected units.")
        reasoning_steps.append(f"Available daily study capacity: {study_hours_per_day} hour(s)/day.")
        
        # 3. Formulate allocation strategy (Revision / Mock Tests)
        reserved_days = 0
        if days_remaining >= 5:
            reserved_days = 2
            reasoning_steps.append("Strategy: Reserving last 2 days for final revision (1 day for Active Revision, 1 day for a Timed Mock Test).")
        elif 3 <= days_remaining < 5:
            reserved_days = 1
            reasoning_steps.append("Strategy: Reserving last 1 day for consolidated final Revision & practice mock exercises.")
        else:
            reserved_days = 0
            reasoning_steps.append("Strategy: Tight schedule constraint (< 3 days). Revision and testing integrated directly into regular study days.")
            
        study_days_available = days_remaining - reserved_days
        reasoning_steps.append(f"Net study days available for new content: {study_days_available} day(s).")
        
        # 4. Distribute topics
        if study_days_available <= 0:
            reasoning_steps.append("CRITICAL: Remaining days are extremely limited! Merging all content and testing into the available timeline.")
            study_days_available = days_remaining
            reserved_days = 0
            
            topics_per_day = math.ceil(num_topics / study_days_available)
            reasoning_steps.append(f"Distributing {num_topics} topics across {study_days_available} day(s) (~{topics_per_day} topics/day).")
            
            for d in range(1, study_days_available + 1):
                start_idx = (d - 1) * topics_per_day
                end_idx = min(start_idx + topics_per_day, num_topics)
                day_topics = flat_topics[start_idx:end_idx]
                if day_topics:
                    tasks_str = " | ".join(day_topics) + " + Quick Revision & Test"
                    plan_days.append({
                        "day": d,
                        "task": f"Study: {tasks_str}",
                        "hours": study_hours_per_day
                    })
        else:
            # Standard case
            if study_days_available >= num_topics:
                reasoning_steps.append("Comfortable schedule: Spreading topics comfortably. Extra days will serve as deep-dive review slots.")
                
                for i, topic in enumerate(flat_topics):
                    plan_days.append({
                        "day": i + 1,
                        "task": f"Study & Notes: {topic}",
                        "hours": study_hours_per_day
                    })
                
                current_day = num_topics + 1
                while current_day <= study_days_available:
                    idx = (current_day - num_topics - 1) % num_topics
                    plan_days.append({
                        "day": current_day,
                        "task": f"Refining and Practicing: Deep review of {flat_topics[idx]}",
                        "hours": study_hours_per_day
                    })
                    current_day += 1
            else:
                reasoning_steps.append(f"Compressed schedule: Bundling {num_topics} topics into {study_days_available} study day(s).")
                
                topics_per_day = num_topics / study_days_available
                for d in range(1, study_days_available + 1):
                    start_idx = int((d - 1) * topics_per_day)
                    end_idx = int(d * topics_per_day)
                    if d == study_days_available:
                        end_idx = num_topics
                    day_topics = flat_topics[start_idx:end_idx]
                    
                    plan_days.append({
                        "day": d,
                        "task": "Study: " + " & ".join(day_topics),
                        "hours": study_hours_per_day
                    })
            
            # Append reserved days
            if reserved_days == 2:
                plan_days.append({
                    "day": days_remaining - 1,
                    "task": "Active Revision: Review summary notes and flashcards for all topics.",
                    "hours": study_hours_per_day
                })
                plan_days.append({
                    "day": days_remaining,
                    "task": "Mock Test: Simulate actual exam environment with timed practice paper.",
                    "hours": study_hours_per_day
                })
            elif reserved_days == 1:
                plan_days.append({
                    "day": days_remaining,
                    "task": "Consolidated Review & Final mock exam review session.",
                    "hours": study_hours_per_day
                })
                
        reasoning_steps.append(f"Successfully generated a custom calendar detailing {len(plan_days)} days of preparation.")
        
        return {
            "success": True,
            "days_remaining": days_remaining,
            "reasoning": reasoning_steps,
            "plan": plan_days
        }

