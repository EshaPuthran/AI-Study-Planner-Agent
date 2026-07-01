"""
gemini_helper.py
----------------
Central Gemini API wrapper for the AI Study Planner Agent.

SDK: google-genai (google.genai) v2+   — the ONLY SDK used in this project.
     Do NOT import google.generativeai anywhere in this codebase.

Behaviour
---------
  • When GEMINI_API_KEY is set to a real key in the .env file:
      → HAS_REAL_KEY = True
      → call_gemini() sends the prompt to Gemini 2.5 Flash and returns the text.
  • When no key (or placeholder key) is found:
      → HAS_REAL_KEY = False
      → call_gemini() routes to get_mock_response(), which generates subject-
        specific mock responses using the topic list embedded in the prompt.
"""

import os
import json
from dotenv import load_dotenv

# ── SDK import (google-genai only) ────────────────────────────────────────────
from google import genai
from google.genai import types

# ── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv()

# ── API key detection ─────────────────────────────────────────────────────────
_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

# True only when a non-empty key that is NOT the placeholder value is present.
HAS_REAL_KEY: bool = bool(_API_KEY and not _API_KEY.startswith("your_"))

# Initialise the client once (None when no key is available).
_client: genai.Client | None = genai.Client(api_key=_API_KEY) if HAS_REAL_KEY else None

_MODEL = "gemini-2.5-flash"


# ── Public helpers ─────────────────────────────────────────────────────────────

def is_api_available() -> bool:
    """Return True when a real Gemini API key is configured."""
    return HAS_REAL_KEY


def call_gemini(
    prompt: str,
    system_instruction: str | None = None,
    response_mime_type: str | None = None,
    raise_exceptions: bool = False,
) -> str:
    """
    Send *prompt* to Gemini and return the response text.

    Falls back to get_mock_response(prompt) when:
      • No real API key is configured (HAS_REAL_KEY is False), OR
      • The Gemini API call raises any exception.

    Args:
        prompt: The user / task prompt.
        system_instruction: Optional system-level instruction for the model.
        response_mime_type: Optional MIME type for structured output
                            (e.g. "application/json").

    Returns:
        A string containing the model's response (or the mock equivalent).
    """
    if not HAS_REAL_KEY:
        return get_mock_response(prompt)

    try:
        config_kwargs: dict = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type

        generate_config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        response = _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=generate_config,
        )
        return response.text

    except Exception as exc:
        if raise_exceptions:
            raise exc
        print(f"[gemini_helper] Gemini API call failed: {exc}. Falling back to mock.")
        return get_mock_response(prompt)


# ── Mock response generator ───────────────────────────────────────────────────

def get_mock_response(prompt: str) -> str:
    """
    Generate a realistic mock response when the Gemini API is unavailable.

    The mock reads the structured content that the calling agent embedded in
    the prompt (e.g. the bullet-list of syllabus topics) so that the output
    contains real subject matter rather than generic placeholders.
    """
    prompt_lower = prompt.lower()

    # ── 0. Chat Assistant (Highest Priority because prompt contains full context) ──
    if "=== new query ===" in prompt_lower:
        return _mock_chat_assistant(prompt)

    # ── 1. Quiz generation ─────────────────────────────────────────────────────
    if "quiz" in prompt_lower or "generate a quiz" in prompt_lower:
        return _mock_quiz(prompt, prompt_lower)

    # ── 2. Notes generation ────────────────────────────────────────────────────
    if "notes" in prompt_lower or "learning materials" in prompt_lower:
        return _mock_notes(prompt)

    # ── 3. Study-plan / recommendation ────────────────────────────────────────
    if "recommend" in prompt_lower:
        return _mock_recommendations()

    # ── 4. Syllabus / topic extraction ────────────────────────────────────────
    if "extract" in prompt_lower or "syllabus" in prompt_lower or "curriculum" in prompt_lower:
        return _mock_syllabus_extraction(prompt)

    return json.dumps({"message": "Mock response: prompt processed successfully."})

# ── Internal mock builders ────────────────────────────────────────────────────

def _mock_chat_assistant(prompt: str) -> str:
    # Try to extract the user query
    query = "your topic"
    for line in prompt.splitlines():
        if line.startswith("Student:"):
            query = line.replace("Student:", "").strip()
            break
            
    return (
        f"**[Mock AI Assistant]** I am responding in offline mode (No Gemini API key).\n\n"
        f"### {query}\n\n"
        f"**Definition:**\n"
        f"This is a fundamental concept in your syllabus that requires careful study. It forms the basis of many advanced topics.\n\n"
        f"**Components:**\n"
        f"- Core principle 1\n"
        f"- Core principle 2\n"
        f"- Integration mechanism\n\n"
        f"**Example:**\n"
        f"In a real-world scenario, you would apply this concept to optimize performance, ensure reliability, or structure your system correctly.\n\n"
        f"**Advantages:**\n"
        f"- Highly efficient and structured.\n"
        f"- Reduces redundancy and errors.\n\n"
        f"**Disadvantages:**\n"
        f"- Can be complex to implement initially.\n"
        f"- Requires strict adherence to protocols.\n\n"
        f"**Exam Tips:**\n"
        f"Focus on understanding the trade-offs and be ready to compare it with alternative approaches. Review your weak topics to ensure you're prepared!\n\n"
        f"*Note: Add a real `GEMINI_API_KEY` to your `.env` file to unlock dynamic, personalized AI explanations!*"
    )

def _extract_topics_from_prompt(prompt: str) -> list[str]:
    """
    Parse the topic bullet list that QuizAgent embeds in prompts.

    QuizAgent injects topics as:
        The following SPECIFIC topics are in scope — questions MUST be based
        exclusively on these:
          - Topic A
          - Topic B
          ...

    This function finds that block and returns the topic strings.
    """
    topics: list[str] = []
    in_block = False
    for line in prompt.splitlines():
        stripped = line.strip()
        if "specific topics are in scope" in stripped.lower():
            in_block = True
            continue
        if in_block:
            if stripped.startswith("- "):
                topics.append(stripped[2:].strip())
            elif stripped == "" or stripped.lower().startswith("parameter") or stripped.lower().startswith("important"):
                if topics:          # end of block
                    break
    return topics


def _extract_scope_from_prompt(prompt: str) -> str:
    """Extract the human-readable quiz scope from 'following scope: "..."'."""
    for line in prompt.splitlines():
        ls = line.strip()
        marker = "following scope:"
        if marker in ls.lower():
            idx = ls.lower().index(marker) + len(marker)
            raw = ls[idx:].strip().strip('"').strip("'").rstrip('."\'')
            if raw:
                return raw
    return "Selected Topic"


def _parse_num_questions(prompt: str) -> int:
    for n in [10, 5, 4, 3, 2, 1]:
        if f"Number of Multiple Choice Questions: {n}" in prompt:
            return n
    return 3


def _parse_difficulty(prompt_lower: str) -> str:
    if "easy" in prompt_lower:
        return "Easy"
    if "hard" in prompt_lower:
        return "Hard"
    return "Medium"


def _mock_quiz(prompt: str, prompt_lower: str) -> str:
    """Build a subject-specific mock quiz from the topics embedded in prompt."""
    scope = _extract_scope_from_prompt(prompt)
    topics = _extract_topics_from_prompt(prompt)
    num_q = _parse_num_questions(prompt)
    difficulty = _parse_difficulty(prompt_lower)

    mcq_list: list[dict] = []
    short_list: list[dict] = []

    if topics:
        # ── Generate generic subject-agnostic questions ──────────────────────
        MCQ_TEMPLATES = [
            lambda t: {
                "question": f"Which of the following BEST describes '{t}'?",
                "options": [
                    f"'{t}' is a core concept that applies fundamentally to this subject.",
                    f"'{t}' is an irrelevant historical footnote.",
                    f"'{t}' is only applicable in extremely rare edge cases.",
                    f"'{t}' cannot be defined in simple terms.",
                ],
                "correct_answer": f"'{t}' is a core concept that applies fundamentally to this subject.",
            },
            lambda t: {
                "question": f"What is the primary purpose of studying '{t}'?",
                "options": [
                    "To build foundational knowledge for advanced applications.",
                    "To memorize facts for standardized testing.",
                    "To avoid learning other topics.",
                    "There is no purpose.",
                ],
                "correct_answer": "To build foundational knowledge for advanced applications.",
            },
            lambda t: {
                "question": f"Which is a key feature of '{t}'?",
                "options": [
                    "It provides a structured way to approach complex problems.",
                    "It is completely random and unpredictable.",
                    "It relies entirely on guesswork.",
                    "It is only useful in theoretical environments.",
                ],
                "correct_answer": "It provides a structured way to approach complex problems.",
            },
        ]

        SA_TEMPLATES = [
            lambda t: {
                "question": f"Define '{t}' and explain its significance.",
                "suggested_answer": (
                    f"'{t}' is a fundamental concept that provides a structured mechanism "
                    f"for understanding this subject. It ensures accurate analysis and supports "
                    f"efficient problem solving."
                ),
            },
            lambda t: {
                "question": f"Describe a real-world scenario where '{t}' is applied.",
                "suggested_answer": (
                    f"'{t}' is applied in various modern industries. For example, professionals "
                    f"rely on principles of '{t}' to optimize workflows, improve accuracy, "
                    f"and deliver robust solutions in complex environments."
                ),
            },
        ]

        for i in range(num_q):
            t = topics[i % len(topics)]
            mcq_fn = MCQ_TEMPLATES[i % len(MCQ_TEMPLATES)]
            sa_fn  = SA_TEMPLATES[i % len(SA_TEMPLATES)]

            mcq_entry = {"id": i + 1, **mcq_fn(t)}
            sa_entry  = {"id": i + 1, **sa_fn(t)}

            mcq_list.append(mcq_entry)
            short_list.append(sa_entry)

        topic_preview = ", ".join(topics[:6]) + ("..." if len(topics) > 6 else "")
        reasoning = (
            f"[Mock AI — no API key] Generated {num_q} question(s) per section "
            f"from {len(topics)} extracted syllabus topic(s): {topic_preview}. "
            f"Add a real GEMINI_API_KEY to .env to receive fully dynamic, AI-generated questions."
        )

    else:
        # ── No topic list available: use scope name but still avoid placeholders ──
        for i in range(num_q):
            mcq_list.append({
                "id": i + 1,
                "question": f"Which concept is central to understanding '{scope}'?",
                "options": [
                    f"Structured analysis of the core principles of '{scope}'.",
                    "Random guess work.",
                    "External factors unrelated to the subject.",
                    "Historical myths.",
                ],
                "correct_answer": f"Structured analysis of the core principles of '{scope}'.",
            })
            short_list.append({
                "id": i + 1,
                "question": f"Explain the significance of '{scope}' in academic study.",
                "suggested_answer": (
                    f"'{scope}' is a core area that underpins the design and implementation of "
                    f"subject-specific knowledge. Mastery of '{scope}' equips students to "
                    f"solve real-world challenges effectively."
                ),
            })
        reasoning = (
            f"[Mock AI — no API key, no topic list] Generic questions generated for scope '{scope}'. "
            f"Upload a syllabus PDF and extract topics first, then regenerate for subject-specific questions."
        )

    quiz_data = {
        "reasoning": reasoning,
        "topic": scope,
        "difficulty": difficulty,
        "multiple_choice": mcq_list,
        "short_answer": short_list,
    }
    return json.dumps(quiz_data)


def _extract_topic_from_notes_prompt(prompt: str) -> str:
    """Pull the topic name from a notes-generation prompt."""
    for line in prompt.splitlines():
        ls = line.strip()
        if "topic:" in ls.lower() or "generate" in ls.lower():
            parts = ls.split(":")
            if len(parts) > 1:
                return parts[-1].replace('"', "").strip()
    return "Selected Topic"


def _extract_note_type(prompt: str) -> str:
    for line in prompt.splitlines():
        ls = line.strip()
        if "note type" in ls.lower() or "type requested" in ls.lower():
            parts = ls.split(":")
            if len(parts) > 1:
                return parts[-1].strip()
    return "Study Notes"


def _mock_notes(prompt: str) -> str:
    target_scope = _extract_topic_from_notes_prompt(prompt)
    note_type = _extract_note_type(prompt)
    topics = _extract_topics_from_prompt(prompt)
    
    if not topics:
        topics = [target_scope]
        
    header = f"### 📚 {note_type}: *{target_scope}*\n\n> **[Mock AI]** No Gemini API key detected. Notes were generated using built-in templates.\n> Add a real `GEMINI_API_KEY` to receive fully personalised AI notes.\n\n---\n\n"
    
    bodies = []
    for topic in topics:
        if "short" in note_type.lower():
            body = f"""#### Concise Summary: {topic}
- **Definition:** {topic} is a foundational concept.
- **Formula/Rule:** X = Y + Z (Applies strictly to {topic}).
- **Keyword 1:** Primary element of {topic}.
- **Keyword 2:** Secondary interaction of {topic}.
- **Core Principle:** Independent isolation.
- **Main Benefit:** Fast execution.
- **Main Drawback:** Complex to configure.
- **Quick Fact:** Widely used in modern systems.
- **Important:** Do not confuse with related theories.
"""
        elif "detailed" in note_type.lower():
            body = f"""#### 1. Detailed Overview: {topic}
{topic} is a foundational concept that governs core principles in this field of study. 
It establishes the rules and structures that ensure robust understanding and application.

#### 2. Core Architecture & Concepts
- **Fundamental Theory**: Describes the logical structure of {topic} and its underlying mechanisms.
- **Practical Application**: Rules and workflows that maintain valid operations in real-world scenarios.

#### 3. Real-world Applications & Examples
When deploying {topic} in a real system, engineers must consider load balancing and data integrity.
For example, an enterprise architecture relies heavily on {topic} for synchronization.

#### 4. Advantages & Disadvantages
**Advantages:**
- High reliability and consistency.
- Standardized implementation.

**Disadvantages:**
- Steep learning curve.
- Overhead in simple scenarios.

#### 5. Exam Tips
When answering questions on {topic}, always provide a diagram and mention the trade-offs!
"""
        elif "exam" in note_type.lower() or "important" in note_type.lower():
            body = f"""#### Frequently Asked Concepts: {topic}
- How does {topic} differ from older methodologies?
- What are the required conditions to implement {topic}?

#### Viva & Short-Answer Questions
**Q:** What is the primary purpose of {topic}?
**A:** To ensure reliable and consistent operations.

**Q:** When does {topic} fail?
**A:** When external conditions breach the theoretical thresholds.

#### Common Mistakes Students Make
- Confusing {topic} with superficial frameworks.
- Forgetting to mention the core formula in answers.
- Misinterpreting the advantages as disadvantages.

#### One-Line Revision Points
- {topic} = Reliability + Consistency.
- Always check the conditions before applying {topic}.
- Remember the mnemonic: **R.E.A.L** (Reliable, Efficient, Accurate, Logical).
"""
        else:
            body = f"#### Overview: {topic}\nGeneral summary for {topic} based on {note_type}."
        
        bodies.append(body)

    return header + "\n\n---\n\n".join(bodies)


def _mock_recommendations() -> str:
    data = {
        "reasoning": (
            "Based on the upcoming exam timeline and incomplete topics, the agent "
            "recommends prioritising high-weightage units and scheduling revision time "
            "before the exam date."
        ),
        "recommendations": [
            {"text": "Focus on completing all remaining core topics in the next 3 days.", "priority": "High"},
            {"text": "Revise previously studied units using the Quiz Generator to test retention.", "priority": "Medium"},
            {"text": "Schedule at least one full mock test session before the exam.", "priority": "High"},
            {"text": "Allocate the last study hour each day to active recall (flashcards, practice questions).", "priority": "Low"},
        ],
    }
    return json.dumps(data)


def _mock_syllabus_extraction(prompt: str) -> str:
    """
    Extract a real-text-based heuristic syllabus from the prompt if the raw PDF
    text was embedded, or return a clearly labelled generic structure.
    The actual heuristic PDF parser (pdf_parser.heuristic_parse_syllabus) is
    invoked directly by pdf_parser.py — this fallback is for edge cases where
    the prompt reaches here without going through the PDF parser first.
    """
    data = {
        "reasoning": (
            "[Mock AI] Gemini API unavailable. The PDF parser's built-in "
            "rule-based heuristic was used instead to extract structure from "
            "the uploaded document."
        ),
        "units": [
            {
                "unit_name": "Unit 1: Introduction & Fundamentals",
                "topics": [
                    "Basic Concepts",
                    "Core Principles",
                    "Terminology",
                ],
            },
            {
                "unit_name": "Unit 2: Theoretical Foundations",
                "topics": [
                    "Underlying Mechanisms",
                    "System Architecture",
                    "Analytical Models",
                ],
            },
            {
                "unit_name": "Unit 3: Practical Applications",
                "topics": [
                    "Implementation Strategies",
                    "Real-world Examples",
                    "Best Practices",
                ],
            },
            {
                "unit_name": "Unit 4: Advanced Topics",
                "topics": [
                    "Optimization Techniques",
                    "Integration Methods",
                    "Future Trends",
                ],
            },
        ],
    }
    return json.dumps(data)
