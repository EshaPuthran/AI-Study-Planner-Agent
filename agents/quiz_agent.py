import json
from utils.gemini_helper import call_gemini

class QuizAgent:
    """
    Educational Quiz Generator Agent.
    Generates targeted quizzes (MCQs and short answers) using Gemini 
    based on the specified syllabus scope and difficulty level.
    """
    def __init__(self):
        pass

    def generate_quiz(self, target_scope, num_questions=3, difficulty="Medium", topics=None):
        """
        Public method to generate a quiz.
        Routes the request through the official MCP Server if available,
        otherwise falls back to the local _generate_quiz_local execution.
        """
        import json
        from utils.mcp_client import execute_mcp_tool
        
        args = {
            "target_scope": target_scope,
            "num_questions": num_questions,
            "difficulty": difficulty,
            "topics_json": json.dumps(topics) if topics else ""
        }
        
        res = execute_mcp_tool("generate_quiz", args)
        if res.get("status") == "success":
            data = res.get("data")
            data["_source"] = "mcp"
            return data
            
        print(f"[MCP Fallback] generate_quiz failed: {res.get('message')}. Using local fallback.")
        data = self._generate_quiz_local(target_scope, num_questions, difficulty, topics)
        data["_source"] = "local"
        return data

    def _generate_quiz_local(self, target_scope, num_questions=3, difficulty="Medium", topics=None):
        """
        Generates a quiz for a given scope (e.g. Unit 1, Multiple Units, or Entire Syllabus) using Gemini.

        Args:
            target_scope (str): Human-readable description of the scope (unit name / "Entire Syllabus").
            num_questions (int): Number of MCQs and short-answer questions to generate.
            difficulty (str): "Easy", "Medium", or "Hard".
            topics (list[str] | None): Optional flat list of topic strings extracted from the syllabus.
                                       When provided they are embedded verbatim into the prompt so
                                       Gemini (or the mock) generates subject-specific questions.
        """
        reasoning_steps = []
        reasoning_steps.append(f"Target Quiz Scope: {target_scope}")
        reasoning_steps.append(f"Difficulty: {difficulty} | Questions per section: {num_questions}")

        # Build the topics block for the prompt
        topics_block = ""
        if topics:
            reasoning_steps.append(f"Topics injected into prompt: {topics}")
            topics_block = (
                "\n\nThe following SPECIFIC topics are in scope — questions MUST be based exclusively on these:\n"
                + "\n".join(f"  - {t}" for t in topics)
            )
        else:
            reasoning_steps.append("No explicit topic list provided; using scope name only.")

        reasoning_steps.append("Formulating educational evaluation using curriculum taxonomy.")

        prompt = f"""
        You are an expert educational examiner. Generate a quiz assessing knowledge on the following scope: "{target_scope}".{topics_block}

        Parameters:
        - Number of Multiple Choice Questions: {num_questions}
        - Number of Short Answer Questions: {num_questions}
        - Difficulty: {difficulty}

        IMPORTANT: Every question and every answer option MUST reference the actual subject matter listed above.
        Do NOT use generic placeholders like "Component A", "Method X", or "Unit 1 definition".

        Provide reasoning explaining the key concepts tested in the "reasoning" key.
        You must return a raw JSON object. Do not wrap the JSON output in markdown formatting.
        The JSON structure MUST follow this schema:
        {{
          "reasoning": "A concise explanation of which chapters/topics in this scope are assessed and why.",
          "topic": "{target_scope}",
          "difficulty": "{difficulty}",
          "multiple_choice": [
            {{
              "id": 1,
              "question": "Question text focusing on key conceptual definitions",
              "options": ["Option A", "Option B", "Option C", "Option D"],
              "correct_answer": "Option A"
            }}
          ],
          "short_answer": [
            {{
              "id": 1,
              "question": "Short answer question text requiring brief explanation",
              "suggested_answer": "Detailed solution guidelines or definition criteria"
            }}
          ]
        }}
        """

        # Also expose the last built prompt so the UI can display it in the debug panel
        self._last_prompt = prompt

        system_instruction = "You are a quiz generation agent that generates educational assessments in valid JSON format only."

        try:
            response_text = call_gemini(prompt, system_instruction=system_instruction, response_mime_type="application/json")
            clean_text = response_text.replace("```json", "").replace("```", "").strip()

            quiz_data = json.loads(clean_text)

            # Extract reasoning returned from model if any
            model_reasoning = quiz_data.get("reasoning", "Model assessed key topics in this unit scope.")
            reasoning_steps.append(f"Model Reasoning: {model_reasoning}")

            return {
                "success": True,
                "reasoning": reasoning_steps,
                "prompt": prompt,
                "data": quiz_data
            }
        except Exception as e:
            print(f"Error parsing generated quiz: {e}")
            reasoning_steps.append(f"Fallback reasoning: System fell back to rules-based parameters because of error: {e}")
            return {
                "success": False,
                "reasoning": reasoning_steps,
                "prompt": prompt,
                "error": f"Failed to parse quiz response: {e}"
            }
