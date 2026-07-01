import json
from utils.gemini_helper import call_gemini

class NotesAgent:
    """
    AI Notes Generator Agent.
    Creates structured, detailed study notes for a specific topic or scope,
    including summaries, definitions, and examples using the Gemini API.
    Supports scalable generation for entire syllabi by chunking per unit.
    """
    def __init__(self):
        pass

    def generate_notes(self, target_scope, note_type="Study Notes", syllabus_units_json="[]", topics=None, progress_callback=None):
        """
        Public method to generate study notes for a topic or scope.
        Routes the request through the official MCP Server if available,
        otherwise falls back to the local _generate_notes_local execution.
        """
        import json
        from utils.mcp_client import execute_mcp_tool
        
        args = {
            "target_scope": target_scope,
            "note_type": note_type,
            "syllabus_units_json": syllabus_units_json,
            "topics_json": json.dumps(topics) if topics else "[]"
        }
        
        res = execute_mcp_tool("generate_ai_notes", args)
        if res.get("status") == "success":
            data = res.get("data")
            data["_source"] = "mcp"
            return data
            
        print(f"[MCP Fallback] generate_ai_notes failed: {res.get('message')}. Using local fallback.")
        data = self._generate_notes_local(target_scope, note_type, syllabus_units_json, topics, progress_callback)
        data["_source"] = "local"
        return data

    def _generate_notes_local(self, target_scope, note_type, syllabus_units_json="[]", topics=None, progress_callback=None):
        """
        Generates study notes. If the scope is large (e.g. multiple units or Entire Syllabus),
        it generates notes unit-by-unit internally and concatenates them to avoid context limits.
        """
        if not topics:
            topics = [target_scope]
            
        reasoning_steps = []
        reasoning_steps.append(f"AI Notes Agent activated for Scope: '{target_scope}'.")
        reasoning_steps.append(f"Target Notes Format: '{note_type}'.")
        
        # Determine if we should generate iteratively unit-by-unit
        try:
            units = json.loads(syllabus_units_json)
        except:
            units = []
            
        needs_chunking = False
        if "detailed" in note_type.lower():
            if len(units) > 3 and (target_scope == "Entire Syllabus" or " & " in target_scope):
                needs_chunking = True
        
        if needs_chunking:
            reasoning_steps.append("Scope is large. Generating unit-by-unit to prevent context limits.")
            all_notes = []
            try:
                for unit in units:
                    unit_name = unit.get("unit_name", "Unit")
                    unit_topics = unit.get("topics", [])
                    # Find intersection with requested topics
                    relevant_topics = [t for t in unit_topics if t in topics]
                    if not relevant_topics:
                        continue
                        
                    msg = f"Generating Unit {len(all_notes) + 1} of {len(units)}: {unit_name}..."
                    if progress_callback: progress_callback(msg)
                    reasoning_steps.append(f"Generating block for {unit_name} ({len(relevant_topics)} topics)...")
                    res = self._generate_notes_block(f"{unit_name}", note_type, syllabus_units_json, relevant_topics)
                    if res.get("success"):
                        all_notes.append(f"## {unit_name}\n\n" + res.get("notes", ""))
                        reasoning_steps.extend(res.get("reasoning", []))
                    else:
                        return res # Propagate error
                        
                return {
                    "success": True,
                    "reasoning": reasoning_steps,
                    "notes": "\n\n---\n\n".join(all_notes)
                }
            except Exception as e:
                reasoning_steps.append(f"Chunking failed: {e}. Falling back to single block generation.")
                return self._generate_notes_block(target_scope, note_type, syllabus_units_json, topics)
        else:
            return self._generate_notes_block(target_scope, note_type, syllabus_units_json, topics)

    def _generate_notes_block(self, target_scope, note_type, syllabus_units_json, topics):
        """
        Inner method to generate a single block of notes.
        """
        reasoning_steps = []
        
        # Build the topics block for the prompt
        topics_block = ""
        if topics:
            topics_block = (
                "\n\nThe following SPECIFIC topics are in scope. Ensure you cover them:\n"
                + "\n".join(f"  - {t}" for t in topics)
            )

        if "short" in note_type.lower():
            type_instructions = """
        - 8–12 concise bullet points
        - Only important definitions, formulas, and keywords
        - No long explanations
        - Designed for a 5-minute quick revision
        """
        elif "detailed" in note_type.lower():
            type_instructions = """
        - Complete, deep explanations of the core concepts
        - Use logical headings and subheadings
        - Detailed examples and use-cases
        - Advantages and Disadvantages where applicable
        - Real-world applications
        - Exam tips
        - Target around 2–4 pages of content
        """
        elif "exam" in note_type.lower() or "important" in note_type.lower():
            type_instructions = """
        - Only frequently asked concepts
        - Viva questions and short-answer points
        - Previous-exam style questions
        - Common mistakes students make
        - Mnemonics if applicable
        - One-line revision points
        - Very exam-oriented and pragmatic
        """
        else:
            type_instructions = f"""
        - Provide a well-structured summary for {note_type}.
        """

        prompt = f"""
        You are an expert academic tutor. Generate high-quality learning materials for the following scope: "{target_scope}".{topics_block}
        
        Context (Syllabus scope):
        {syllabus_units_json}
        
        Note Type Requested: {note_type}
        
        Please structure your output in clean Markdown formatting strictly adhering to the following format requirements:
        {type_instructions}
        
        Do not include generic placeholders—use actual domain concepts relevant to the scope "{target_scope}".
        """
        
        system_instruction = "You are a professional academic notes writer that outputs clean educational resources."
        
        try:
            response_text = call_gemini(prompt, system_instruction=system_instruction)
            reasoning_steps.append(f"Successfully generated notes on '{target_scope}' ({len(response_text)} chars).")
            return {
                "success": True,
                "reasoning": reasoning_steps,
                "notes": response_text
            }
        except Exception as e:
            print(f"Error generating notes block: {e}")
            reasoning_steps.append(f"Error encountered during note generation: {e}")
            return {
                "success": False,
                "reasoning": reasoning_steps,
                "error": str(e)
            }
