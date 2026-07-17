"""ReAct-style Course Planning Agent for ASMAJ1446A.

This module provides a CoursePlanningAgent that follows a simple
Reason → Act → Observe → Answer loop.  It uses the model abstraction
layer from ``src.model`` for reasoning and answer generation, and the
tool registry from ``src.tool_registry`` for tool execution.

No external LLM APIs are called — the default model is MockModel.
"""

import json
from pathlib import Path

from src.model import BaseModelInterface, MockModel
from src.tool_registry import TOOL_REGISTRY, get_tool, list_tools

# Project root is the parent directory of src/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_course_planning_skill() -> str:
    """Load the course planning skill instructions from the SKILL.md file.

    Returns:
        The markdown content of ``skills/course_planning/SKILL.md``.

    Raises:
        FileNotFoundError: If the SKILL.md file does not exist at the
            expected path.
    """
    path = _PROJECT_ROOT / "skills" / "course_planning" / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Course planning skill file not found: {path}"
        )
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------
# structured action parser
# ------------------------------------------------------------------


def parse_tool_action(response: str) -> dict:
    """Parse a model response into a structured tool-calling action.

    Supports the following JSON formats:

    * Explicit tool action — ``{"action": "tool", "tool_name": ...,
      "arguments": {...}}``
    * Explicit finish — ``{"action": "finish"}``
    * Legacy (no ``action`` field) — ``{"tool_name": ...,
      "arguments": {...}}``, treated as ``action: "tool"``
    * JSON with surrounding text — the parser finds the first ``{``
      and last ``}``.
    * JSON inside a markdown code block — `` ```json ... ``` ``.

    Args:
        response: A raw string from the model.

    Returns:
        A dict with keys ``action``, ``valid``, ``tool_name``,
        ``arguments``, and ``error``.
    """
    json_str = _extract_json(response)
    if json_str is None:
        return {
            "action": None,
            "valid": False,
            "tool_name": None,
            "arguments": None,
            "error": "No JSON action block found in model response.",
        }

    try:
        action_obj = json.loads(json_str)
    except json.JSONDecodeError as exc:
        return {
            "action": None,
            "valid": False,
            "tool_name": None,
            "arguments": None,
            "error": f"Malformed JSON in model response: {exc}",
        }

    # Determine action type — explicit or legacy.
    action_type = action_obj.get("action")

    if action_type == "finish":
        return {
            "action": "finish",
            "valid": True,
            "tool_name": None,
            "arguments": None,
            "error": None,
        }

    if action_type == "clarify":
        question = action_obj.get("question", "")
        if not isinstance(question, str) or not question.strip():
            return {
                "action": "clarify",
                "valid": False,
                "tool_name": None,
                "arguments": None,
                "error": "Clarify action requires a non-empty 'question' string.",
            }
        return {
            "action": "clarify",
            "valid": True,
            "tool_name": None,
            "arguments": None,
            "error": None,
            "question": question.strip(),
        }

    # Legacy format (no "action" field) is treated as tool.
    if action_type is None:
        action_type = "tool"
    elif action_type != "tool":
        return {
            "action": None,
            "valid": False,
            "tool_name": None,
            "arguments": None,
            "error": f"Unknown action type: '{action_type}'. "
                      "Expected 'tool' or 'finish'.",
        }

    # --- tool action validation ---
    tool_name = action_obj.get("tool_name")
    arguments = action_obj.get("arguments")

    if not tool_name:
        return {
            "action": "tool",
            "valid": False,
            "tool_name": None,
            "arguments": arguments,
            "error": "Action is missing 'tool_name'.",
        }

    tool_meta = get_tool(tool_name)
    if tool_meta is None:
        return {
            "action": "tool",
            "valid": False,
            "tool_name": tool_name,
            "arguments": arguments,
            "error": f"Unknown tool: '{tool_name}'.",
        }

    if not isinstance(arguments, dict):
        return {
            "action": "tool",
            "valid": False,
            "tool_name": tool_name,
            "arguments": arguments,
            "error": "'arguments' must be a dict.",
        }

    required_args = tool_meta["required_args"]
    missing = [f for f in required_args if f not in arguments]
    if missing:
        return {
            "action": "tool",
            "valid": False,
            "tool_name": tool_name,
            "arguments": arguments,
            "error": f"Missing required arguments: {missing}.",
        }

    return {
        "action": "tool",
        "valid": True,
        "tool_name": tool_name,
        "arguments": arguments,
        "error": None,
    }


def _extract_json(response: str) -> str | None:
    """Extract a JSON string from a model response.

    Tries two strategies in order:
    1. Markdown code block — `` ```json ... ``` ``
    2. Braces — first ``{`` to last ``}``

    Returns:
        The extracted JSON substring, or ``None`` if no JSON found.
    """
    # Strategy 1: markdown code block with optional language tag.
    import re

    match = re.search(
        r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL
    )
    if match:
        return match.group(1).strip()

    # Strategy 2: first { to last }
    start = response.find("{")
    end = response.rfind("}")
    if start != -1 and end != -1 and start < end:
        return response[start : end + 1]

    return None


def _format_recommendation_observation(
    courses: list[dict], requirement_tag: str
) -> str:
    """Format a recommendation result into a concise observation string.

    Includes the total count and a preview of the first 10 courses with
    key fields so the model can produce a specific final answer.

    Args:
        courses: List of course recommendation dicts.
        requirement_tag: The requirement tag that was queried.

    Returns:
        A formatted observation string.
    """
    total = len(courses)

    if total == 0:
        return f"No courses found for requirement tag: '{requirement_tag}'."

    preview_count = min(total, 10)
    lines = [
        f"Found {total} courses for '{requirement_tag}'.",
        "",
        f"Preview ({preview_count} of {total}):",
        "",
    ]

    for i, course in enumerate(courses[:preview_count], start=1):
        code = course.get("course_code", "?")
        title = course.get("title", "Unknown")
        dept = course.get("department", "")
        level = course.get("level", "")
        credits = course.get("credits", "")
        breadth = course.get("breadth_name", "")
        terms = ", ".join(course.get("term_availability", [])) or "N/A"
        verification = course.get("verification_status", "")
        prereq = course.get("prerequisite_status", "")
        interest_match = course.get("interest_match", None)
        matched_interests = course.get("matched_interests", None)

        block = (
            f"{i}. {code} — {title}\n"
            f"   Department: {dept} | Level: {level} | Credits: {credits}\n"
            f"   Breadth: {breadth} | Terms: {terms}\n"
            f"   Verification: {verification} | Prerequisites: {prereq}"
        )

        # Append interest info when available.
        if interest_match is not None:
            match_label = (
                f"interests: {', '.join(matched_interests)}"
                if matched_interests
                else "interests: none"
            )
            block += f"\n   Interest match: {interest_match} ({match_label})"

        lines.append(block)

    return "\n".join(lines)


class CoursePlanningAgent:
    """A ReAct-style agent for course planning.

    The agent follows a Reason → Act → Observe → Answer loop:

    1. **Reason** — analyse the user request via the model.
    2. **Act** — parse a structured tool action and call the tool.
    3. **Observe** — capture the tool result.
    4. **Answer** — generate a final response via the model.

    Tool metadata and functions are loaded from
    :mod:`src.tool_registry`.

    Attributes:
        completed_courses: Course codes the student has completed.
        skill_instructions: Loaded SKILL.md content.
        model: The language model backend (defaults to MockModel).
    """

    def __init__(
        self,
        completed_courses: list[str] | None = None,
        model: BaseModelInterface | None = None,
    ):
        """Initialise the agent.

        Args:
            completed_courses: Course codes the student has completed.
                Defaults to an empty list.
            model: A :class:`BaseModelInterface` instance.  Defaults to
                :class:`MockModel`.
        """
        self.completed_courses = completed_courses or []
        self.skill_instructions = load_course_planning_skill()
        self.model = model if model is not None else MockModel()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def handle_request(
        self, user_request: str, max_tool_steps: int = 2
    ) -> dict:
        """Run the bounded multi-step ReAct loop for a user request.

        The agent asks the model for actions up to *max_tool_steps* times.
        Each valid tool action is executed and its observation is fed back
        into the next reasoning step.  The loop stops on an explicit
        ``{"action": "finish"}``, when *max_tool_steps* is reached, on a
        repeated identical tool call, or on a parse error.

        Args:
            user_request: A natural-language string from the student.
            max_tool_steps: Maximum number of tool calls to make before
                stopping (default 2).

        Returns:
            A dict with keys:
                * ``thought`` — raw response from the first step
                * ``tool_called`` — tool name from the first step
                * ``observation`` — observation from the first step
                * ``final_answer`` — final synthesised response
                * ``steps`` — list of all step dicts
                * ``stop_reason`` — one of ``"finish"``,
                  ``"max_steps"``, ``"parse_error"``,
                  ``"repeated_action"``, ``"no_action"``
                * ``last_model_response`` — raw response from the most
                  recent reasoning call (useful for debugging)
                * ``parse_error`` — parser error message when
                  *stop_reason* is ``"parse_error"``, else ``None``
        """
        steps: list[dict] = []
        stop_reason: str = "no_action"
        seen_calls: set[tuple] = set()
        last_thought: str = ""
        parsed: dict | None = None

        for _step_idx in range(max_tool_steps):
            last_thought = self._reason_about_request(
                user_request, prior_steps=steps if steps else None
            )
            parsed = parse_tool_action(last_thought)

            if parsed["action"] == "finish":
                stop_reason = "finish"
                break

            if parsed["action"] == "clarify":
                stop_reason = "clarify"
                break

            if parsed["action"] is None or not parsed["valid"]:
                stop_reason = "parse_error" if steps else "no_action"
                break

            # Guard against repeated identical tool calls.
            # Use stable JSON serialisation to handle list/nested values.
            call_key = (
                parsed["tool_name"],
                json.dumps(parsed["arguments"], sort_keys=True),
            )
            if call_key in seen_calls:
                stop_reason = "repeated_action"
                break
            seen_calls.add(call_key)

            observation = self._call_tool(
                parsed["tool_name"], parsed["arguments"]
            )
            steps.append({
                "thought": last_thought,
                "tool_called": parsed["tool_name"],
                "arguments": parsed["arguments"],
                "observation": observation,
            })
        else:
            # for-else: loop completed all iterations without breaking.
            stop_reason = "max_steps"

        # --- generate final answer ---------------------------------------
        if stop_reason == "clarify":
            # Clarification question is the final answer — no model call.
            final_answer = parsed.get("question", "") if parsed else ""
        elif steps:
            final_answer = self._generate_answer(user_request, steps)
        else:
            error_msg = parsed["error"] if parsed else "No action taken."
            final_answer = (
                "I could not determine which action to take. "
                f"Please try rephrasing your request. ({error_msg})"
            )

        # --- backward-compatible flat keys -------------------------------
        parse_error = (
            parsed["error"] if parsed and stop_reason == "parse_error"
            else None
        )
        if steps:
            return {
                "thought": steps[0]["thought"],
                "tool_called": steps[0]["tool_called"],
                "observation": steps[0]["observation"],
                "final_answer": final_answer,
                "steps": steps,
                "stop_reason": stop_reason,
                "last_model_response": last_thought,
                "parse_error": parse_error,
            }
        elif stop_reason == "clarify":
            return {
                "thought": last_thought,
                "tool_called": None,
                "observation": "Clarification required.",
                "final_answer": final_answer,
                "steps": steps,
                "stop_reason": stop_reason,
                "last_model_response": last_thought,
                "parse_error": None,
            }
        else:
            return {
                "thought": last_thought,
                "tool_called": None,
                "observation": (
                    parsed["error"] if parsed else "No action taken."
                ),
                "final_answer": final_answer,
                "steps": steps,
                "stop_reason": stop_reason,
                "last_model_response": last_thought,
                "parse_error": parse_error,
            }

    def get_skill_summary(self) -> dict:
        """Return a summary of the loaded skill instructions."""
        loaded = bool(self.skill_instructions)
        return {
            "skill_loaded": loaded,
            "skill_length": len(self.skill_instructions) if loaded else 0,
        }

    # ------------------------------------------------------------------
    # ReAct step implementations
    # ------------------------------------------------------------------

    def _reason_about_request(
        self,
        user_request: str,
        prior_steps: list[dict] | None = None,
    ) -> str:
        """Generate a reasoning thought with a structured action.

        The model is prompted with the full tool registry.  When
        *prior_steps* is provided, prior tool calls and their
        observations are injected into the message history so the
        model knows what has already been done.

        Args:
            user_request: The student's original query.
            prior_steps: Previous tool steps (``thought``,
                ``tool_called``, ``observation``).  ``None`` on the
                first call.

        Returns:
            The raw model response string.
        """
        # Build a detailed Available Tools section from the registry.
        tool_entries: list[str] = []
        for name in sorted(TOOL_REGISTRY.keys()):
            meta = TOOL_REGISTRY[name]
            desc = meta["description"]
            required = json.dumps(meta["required_args"])
            tool_entries.append(f"- **{name}**: {desc}\n"
                                f"  Required arguments: {required}")

        tools_section = "\n".join(tool_entries)
        completed = json.dumps(self.completed_courses)

        system_prompt = (
            "You are a UofT course planning assistant. "
            "Analyse the student's request and decide which "
            "tool to call next.\n\n"
            "## Available Tools\n\n"
            f"{tools_section}\n\n"
            "## Tool-Selection Guidance\n\n"
            "Choose the tool that matches the question type:\n\n"
            '| Question type | Tool |\n'
            "|---|---|\n"
            '| "Can I take ...", "Am I eligible ...", prerequisite '
            "or completed-course questions | "
            "**check_prerequisites** |\n"
            '| "Is ... offered in Fall/Winter", target term, '
            "term availability | "
            "**check_term_availability** |\n"
            '| "What courses should I take", "recommend ...", '
            "program pool, interest-based | "
            "**recommend_courses_for_requirement** |\n"
            '| General course info — title, description, '
            "department, credits | **get_course_details** |\n"
            '| Exclusion questions, overlapping credit, '
            "course conflicts | **check_exclusions** |\n"
            '| Verification status, needs_official_verification, '
            "UNKNOWN metadata, manual review | "
            "**get_course_metadata_status** |\n"
            '| "Should I take COURSE for PROGRAM requirement", '
            "named course + program pathway questions | "
            "**get_course_metadata_status** first, then "
            "**recommend_courses_for_requirement** with the "
            "correct program requirement tag |\n\n"
            "**Important:** get_course_details is for general "
            "metadata only (title, description, department, "
            "credits) — it does NOT check prerequisite "
            "eligibility, target-term availability, exclusions, "
            "or verification status.  Use the dedicated tools: "
            "check_prerequisites, check_term_availability, "
            "check_exclusions, get_course_metadata_status.  "
            "Pick the right tool for each part of the question.\n\n"
            "## Requirement-Tag Mapping\n\n"
            "Use the correct requirement_tag for program pathways:\n\n"
            '| Program requirement | requirement_tag |\n'
            "|---|---|\n"
            '| First-year math pathway | '
            "**first_year_math_pathway** |\n"
            '| First-year introductory CS pathway | '
            "**first_year_intro_cs_pathway** |\n"
            '| Second-year statistics choice | '
            "**second_year_statistics_choice** |\n"
            '| Computational Cognition Stream approved pool | '
            "**computational_cognition_stream_pool** |\n"
            '| Fourth-year capstone choice | '
            "**fourth_year_capstone_choice** |\n\n"
            "If the user asks about AI, machine learning, or "
            "Computational Cognition Stream course options, use:\n\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "recommend_courses_for_requirement",\n'
            '  "arguments": {\n'
            '    "requirement_tag": '
            '"computational_cognition_stream_pool",\n'
            f'    "completed_courses": {completed},\n'
            '    "interests": ["AI", "machine learning"]\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "When the student expresses specific interests, always "
            "include the ``interests`` argument — it will rank "
            "matching courses first.  ``interests`` is optional; "
            "omit it only when the student has no particular focus.\n\n"
            f"The student's completed courses are: {completed}\n"
            "Always use these exact completed courses — do not "
            "invent or modify them.\n\n"
            "## Multi-Part Query Example\n\n"
            "For a query with BOTH eligibility AND a target "
            "term, check prerequisites first, then term "
            "availability, then finish:\n\n"
            "User: \"Can I take CSC384H1 in Winter if I "
            "completed CSC148H1 and STA237H1?\"\n\n"
            "Step 1 — check eligibility:\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "check_prerequisites",\n'
            '  "arguments": {\n'
            '    "course_code": "CSC384H1",\n'
            '    "completed_courses": ["CSC148H1", "STA237H1"]\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "Step 2 — check term availability:\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "check_term_availability",\n'
            '  "arguments": {\n'
            '    "course_code": "CSC384H1",\n'
            '    "target_term": "Winter"\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "Step 3 — done collecting evidence:\n"
            "```json\n"
            '{"action": "finish"}\n'
            "```\n\n"
            "## Named Course + Program Pathway Example\n\n"
            "For a query about whether a specific course satisfies "
            "a program requirement, check verification metadata "
            "first, then retrieve the relevant pathway:\n\n"
            "User: \"Should I take MAT137Y1 for the math "
            "requirement in the Cognitive Science Computational "
            "Cognition stream?\"\n\n"
            "Step 1 — check verification status:\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "get_course_metadata_status",\n'
            '  "arguments": {\n'
            '    "course_code": "MAT137Y1"\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "Step 2 — retrieve math pathway options:\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "recommend_courses_for_requirement",\n'
            '  "arguments": {\n'
            '    "requirement_tag": "first_year_math_pathway",\n'
            f'    "completed_courses": {completed}\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "Step 3 — done:\n"
            "```json\n"
            '{"action": "finish"}\n'
            "```\n\n"
            "## Clarification\n\n"
            "Use action=\"clarify\" when the student has not provided "
            "enough information to proceed.  Ask only for what is "
            "missing — completed courses, target term, program, or "
            "specific course code.  Do not invent missing information "
            "and do not provide course advice before getting it.\n\n"
            "Example — vague query:\n"
            'User: "What course should I take next?"\n'
            "```json\n"
            "{\n"
            '  "action": "clarify",\n'
            '  "question": "Which courses have you completed, what '
            "program or stream are you in, and which term are you "
            'planning for?"\n'
            "}\n"
            "```\n\n"
            "## Other Examples\n\n"
            "Exclusion check:\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "check_exclusions",\n'
            '  "arguments": {\n'
            '    "course_code": "CSC148H1",\n'
            '    "completed_courses": ["CSC108H1"]\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "Verification / metadata check:\n"
            "```json\n"
            "{\n"
            '  "action": "tool",\n'
            '  "tool_name": "get_course_metadata_status",\n'
            '  "arguments": {\n'
            '    "course_code": "MAT137Y1"\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "## Rules\n\n"
            "1. Output exactly one JSON object.\n"
            '2. Use {"action": "tool", "tool_name": "...", '
            '"arguments": {...}} when you need to call a tool.\n'
            '3. Legacy format {"tool_name": "...", "arguments": {...}} '
            "is also accepted.\n"
            '4. Use {"action": "finish"} when you have collected '
            "enough tool evidence to answer the question.\n"
            "5. Use only the argument names listed in Required "
            "arguments above.\n"
            "6. Do not output explanatory text before or after "
            "the JSON.\n"
            "7. Do not repeat a tool call with identical arguments.\n"
            "8. Never invent tool results — only use what the "
            "tools actually return.\n"
            "9. For multi-part questions (eligibility + term): "
            "call check_prerequisites FIRST, then "
            "check_term_availability.  Do NOT skip to term "
            "availability before checking prerequisites.\n"
            "10. Use action=\"clarify\" when essential information is "
            "missing.  Ask a specific question targeting only the "
            "missing information.  Do not invent data or give "
            "course advice before receiving it.\n"
            "11. Never infer that a course is absent from a full "
            "result set merely because it is absent from a preview. "
            "The observation preview shows at most 10 courses from "
            "a potentially larger list.  Only conclude presence or "
            "absence from explicit tool observations.\n"
            "12. Never claim a course does or does not satisfy a "
            "program requirement unless a tool observation supports "
            "that conclusion.  Preserve needs_official_verification "
            "and UNKNOWN statuses.  When a course is unverified, "
            "explain that status before giving a recommendation. "
            "Suggest alternatives only when they appear in "
            "retrieved tool observations."
        )

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
        ]

        # Inject prior tool steps so the model knows what happened.
        if prior_steps:
            context_lines: list[str] = [
                "## Completed tool steps",
                "",
                "The following tools have already been called. "
                "Do NOT repeat any of these tool calls with the "
                "same arguments.",
                "",
            ]
            for i, step in enumerate(prior_steps, start=1):
                tool = step["tool_called"]
                args = step.get("arguments", {})
                obs = step["observation"]
                context_lines.append(
                    f"Step {i}: {tool}\n"
                    f"  Arguments: {json.dumps(args)}\n"
                    f"  Observation: {obs}\n"
                )
            context_lines.append(
                "Identify which part of the user's question is "
                "still unanswered.  Choose the next tool that "
                "directly addresses that remaining part.  If "
                "all parts are answered, use action='finish'."
            )

            messages.append({
                "role": "system",
                "content": "\n".join(context_lines),
            })

        messages.append({"role": "user", "content": user_request})
        return self.model.generate_response(messages)

    def _call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool via the registry with parsed arguments.

        Args:
            tool_name: Name of the tool from the tool registry.
            arguments: Dict of argument values for the tool.

        Returns:
            A human-readable observation string.
        """
        tool_meta = get_tool(tool_name)
        if tool_meta is None:
            return f"Unknown tool: '{tool_name}'."

        func = tool_meta["function"]

        try:
            result = func(**arguments)

            if tool_name == "get_course_details":
                if result is None:
                    return "Course not found in catalog."
                return (
                    f"Found course: {result.get('title', 'Unknown')} "
                    f"({arguments.get('course_code', '?')})."
                )

            if tool_name == "check_prerequisites":
                return (
                    f"Prerequisite check for "
                    f"{arguments.get('course_code', '?')}: "
                    f"{result['status']}."
                )

            if tool_name == "recommend_courses_for_requirement":
                return _format_recommendation_observation(
                    result, arguments.get("requirement_tag", "?")
                )

            if tool_name == "check_exclusions":
                if result.get("has_conflict"):
                    conflicts = ", ".join(
                        result.get("conflicting_courses", [])
                    )
                    return (
                        f"Exclusion conflict found for "
                        f"{result.get('course_code', '?')}: "
                        f"{conflicts}. {result.get('message', '')}"
                    )
                return (
                    f"No exclusion conflicts for "
                    f"{result.get('course_code', '?')}. "
                    f"{result.get('message', '')}"
                )

            if tool_name == "get_course_metadata_status":
                code = result.get("course_code", "?")
                status = result.get("verification_status", "?")
                notes = result.get("notes", [])
                needs_review = result.get("needs_manual_review", False)
                review = "manual review needed" if needs_review else "ok"
                notes_str = "; ".join(notes) if notes else "no concerns"
                return (
                    f"Metadata for {code}: verification={status}, "
                    f"review={review}. {notes_str}."
                )

            return f"Tool '{tool_name}' returned: {result}"

        except TypeError as exc:
            return f"Argument mismatch for '{tool_name}': {exc}."
        except Exception as exc:
            return f"Tool '{tool_name}' failed: {exc}."

    def _generate_answer(
        self, user_request: str, steps: list[dict]
    ) -> str:
        """Generate a final answer from all accumulated tool observations.

        Args:
            user_request: The student's original query.
            steps: List of step dicts, each containing ``thought``,
                ``tool_called``, and ``observation``.

        Returns:
            A synthesised final answer string.
        """
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are a UofT course planning assistant. "
                    "Given the student's request, your reasoning steps, "
                    "and the tool results, write a concise final answer.\n\n"
                    "## Evidence Attribution\n\n"
                    "Attribute every status to the specific tool that "
                    "produced it.  Distinguish clearly among:\n"
                    "- prerequisite eligibility (from check_prerequisites)\n"
                    "- metadata verification (from get_course_metadata_status)\n"
                    "- term availability (from check_term_availability)\n"
                    "- program-pathway membership (from "
                    "recommend_courses_for_requirement)\n\n"
                    "Do not attach a course-level metadata warning (such "
                    "as needs_official_verification or manual review) to "
                    "a prerequisite eligibility result.  If "
                    "check_prerequisites returns eligible, say only that "
                    "the deterministic prerequisite check returned "
                    "eligible.  If get_course_metadata_status returns "
                    "needs_official_verification or manual review needed, "
                    "explain that this applies to the course metadata or "
                    "official-status verification.  Do not combine these "
                    "into one unsupported causal statement.\n\n"
                    "## Pathway Wording\n\n"
                    "When a course appears in a "
                    "recommend_courses_for_requirement result for a "
                    "program pathway, say: \"The course is listed as an "
                    "option in the retrieved [pathway name].\"  Do not "
                    "automatically say the course is \"recommended\" or "
                    "that the student \"should take\" it.  For unverified "
                    "courses, preferred wording: \"[COURSE] appears in "
                    "the retrieved [pathway] data, but its metadata is "
                    "marked [verification_status] and its term "
                    "availability is [status].  The prerequisite checker "
                    "returned [status], but that does not resolve the "
                    "separate official-verification warning.\"\n\n"
                    "## Pathway Alternatives\n\n"
                    "When the user asks about a named course for a program "
                    "pathway and the named course has verification "
                    "uncertainty or UNKNOWN data, help the student continue "
                    "planning by mentioning a small number of relevant "
                    "alternatives from the retrieved pathway observation. "
                    "Use wording such as: \"Other options listed in the "
                    "retrieved [pathway name] include [courses].\"  Limit "
                    "alternatives to at most three options.  Prefer "
                    "alternatives with stronger verification status and "
                    "known term information.\n\n"
                    "Describe alternatives as retrieved options, not "
                    "automatic recommendations.  Do not say they are "
                    "\"better\", that the student \"should take\" them, "
                    "that they are \"definitely available\", or that they "
                    "\"definitely satisfy\" the student's plan.  Preserve "
                    "each alternative's observed verification status and "
                    "term availability — do not remove or soften "
                    "needs_official_verification, UNKNOWN, or "
                    "manual_review_needed for any course.  Suggest "
                    "official verification before the student makes a "
                    "final decision.\n\n"
                    "## General Rules\n\n"
                    "State only claims supported by the observations. "
                    "Do not invent prerequisites, term offerings, or "
                    "program rules. "
                    "Preserve UNKNOWN, manual_review_needed, and "
                    "verification warnings exactly as reported."
                ),
            },
            {"role": "user", "content": user_request},
        ]

        for step in steps:
            messages.append({
                "role": "assistant",
                "content": step["thought"],
            })
            messages.append({
                "role": "system",
                "content": (
                    f"Tool result ({step['tool_called']}): "
                    f"{step['observation']}"
                ),
            })

        return self.model.generate_response(messages)
