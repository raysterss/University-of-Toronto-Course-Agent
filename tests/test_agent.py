"""Tests for src/agent.py — ReAct-style CoursePlanningAgent."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent import (
    CoursePlanningAgent,
    _format_recommendation_observation,
    load_course_planning_skill,
    parse_tool_action,
)
from src.model import BaseModelInterface, MockModel


# ---------------------------------------------------------------------------
# Spy model — captures the prompt messages sent by the agent
# ---------------------------------------------------------------------------


class _SpyModel(BaseModelInterface):
    """A test model that records the messages passed to generate_response."""

    def __init__(self) -> None:
        self.last_messages: list[dict] = []

    def generate_response(self, messages: list[dict]) -> str:
        self.last_messages = messages
        return "Spy model response"


# ---------------------------------------------------------------------------
# Skill loading
# ---------------------------------------------------------------------------

def test_skill_file_loads_successfully():
    """load_course_planning_skill() returns non-empty markdown content."""
    content = load_course_planning_skill()
    assert isinstance(content, str)
    assert len(content) > 0
    assert "Course Planning" in content


def test_agent_contains_skill_instructions():
    """Agent loads skill instructions on initialisation."""
    agent = CoursePlanningAgent()
    assert isinstance(agent.skill_instructions, str)
    assert len(agent.skill_instructions) > 0

    summary = agent.get_skill_summary()
    assert summary["skill_loaded"] is True
    assert summary["skill_length"] > 0


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_agent_initialises():
    """Agent can initialise with and without completed courses."""
    agent_default = CoursePlanningAgent()
    assert agent_default.completed_courses == []

    agent_with = CoursePlanningAgent(["COG100H1", "CSC108H1"])
    assert agent_with.completed_courses == ["COG100H1", "CSC108H1"]


def test_agent_accepts_custom_model():
    """Agent can accept a custom model instance."""
    model = MockModel()
    agent = CoursePlanningAgent(model=model)
    assert agent.model is model


# ---------------------------------------------------------------------------
# ReAct loop — reasoning step
# ---------------------------------------------------------------------------

def test_agent_can_perform_reasoning_step():
    """Agent generates a thought via _reason_about_request."""
    agent = CoursePlanningAgent()
    thought = agent._reason_about_request(
        "I want to take machine learning courses"
    )
    assert isinstance(thought, str)
    assert len(thought) > 0


# ---------------------------------------------------------------------------
# Reasoning prompt content — verifies the model receives proper tool schemas
# ---------------------------------------------------------------------------


class TestReasoningPrompt:
    """Verify that _reason_about_request sends a complete prompt to the model."""

    @staticmethod
    def _get_system_prompt(agent: CoursePlanningAgent, request: str) -> str:
        """Return the system prompt the agent sends to the model."""
        spy = _SpyModel()
        agent.model = spy
        agent._reason_about_request(request)
        for msg in spy.last_messages:
            if msg["role"] == "system":
                return msg["content"]
        return ""

    def test_prompt_includes_all_tool_names(self):
        """Prompt lists all three tools from the registry."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert "get_course_details" in prompt
        assert "check_prerequisites" in prompt
        assert "recommend_courses_for_requirement" in prompt

    def test_prompt_includes_requirement_tag(self):
        """Prompt mentions requirement_tag as a required argument."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert "requirement_tag" in prompt

    def test_prompt_includes_completed_courses_arg(self):
        """Prompt mentions completed_courses as a required argument."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert "completed_courses" in prompt

    def test_prompt_includes_stream_pool_tag(self):
        """Prompt shows the computational_cognition_stream_pool tag."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert "computational_cognition_stream_pool" in prompt

    def test_prompt_includes_agent_completed_courses(self):
        """Prompt encodes the agent's stored completed courses."""
        agent = CoursePlanningAgent(["CSC108H1", "CSC148H1", "STA237H1"])
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert "CSC108H1" in prompt
        assert "CSC148H1" in prompt
        assert "STA237H1" in prompt

    def test_prompt_includes_output_rules(self):
        """Prompt tells the model to output only one JSON action block."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert "exactly one json" in prompt.lower()
        assert "do not output explanatory text" in prompt.lower()

    def test_prompt_key_mapping_includes_example_json(self):
        """Prompt includes the exact example JSON for the stream pool."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert '"tool_name": "recommend_courses_for_requirement"' in prompt
        assert '"requirement_tag": "computational_cognition_stream_pool"' in prompt

    def test_prompt_includes_interests_in_example(self):
        """Prompt example JSON includes interests argument."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        assert '"interests": ["AI", "machine learning"]' in prompt

    # -- tool-selection guidance ------------------------------------------

    def test_prompt_guides_eligibility_to_check_prerequisites(self):
        """Eligibility / 'can I take' questions → check_prerequisites."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC384H1?")

        assert "check_prerequisites" in prompt.lower()
        assert "can i take" in prompt.lower() or (
            "am i eligible" in prompt.lower()
        )

    def test_prompt_guides_term_to_check_term_availability(self):
        """Term availability questions → check_term_availability."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Is CSC384H1 offered?")

        assert "check_term_availability" in prompt.lower()
        assert "target_term" in prompt.lower()
        assert "winter" in prompt.lower()

    def test_prompt_states_get_course_details_limitations(self):
        """Prompt warns get_course_details does NOT check prereqs or term."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses")

        lowered = prompt.lower()
        assert "get_course_details" in lowered
        assert "does not check prerequisite" in lowered.lower() or (
            "does not check" in lowered and "prerequisite" in lowered
        )
        assert "does not check" in lowered and "term" in lowered

    # -- multi-part example -----------------------------------------------

    def test_prompt_includes_csc384h1_multistep_example(self):
        """Prompt shows the two-step CSC384H1 eligibility+term example."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC384H1?")

        assert "CSC384H1" in prompt
        assert "CSC148H1" in prompt
        assert "STA237H1" in prompt
        assert '"action": "finish"' in prompt
        assert "check_term_availability" in prompt
        assert '"target_term": "Winter"' in prompt

    def test_prompt_multistep_example_order(self):
        """Example shows check_prerequisites BEFORE check_term_availability."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC384H1?")

        prereq_pos = prompt.find("check_prerequisites")
        term_pos = prompt.find("check_term_availability")
        assert prereq_pos < term_pos, (
            "Expected check_prerequisites before check_term_availability "
            "in the example"
        )

    # -- new tool guidance -------------------------------------------------

    def test_prompt_maps_exclusion_to_check_exclusions(self):
        """Exclusion/conflict questions → check_exclusions."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Check exclusions.")

        assert "check_exclusions" in prompt.lower()
        assert "exclusion" in prompt.lower()

    def test_prompt_maps_verification_to_metadata_status(self):
        """Verification questions → get_course_metadata_status."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Check verification.")

        assert "get_course_metadata_status" in prompt.lower()
        assert "verification" in prompt.lower()

    def test_prompt_warns_get_course_details_not_for_exclusions(self):
        """Prompt says get_course_details is NOT for exclusions or
        verification."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Recommend AI courses.")

        lowered = prompt.lower()
        assert "get_course_details" in lowered
        assert "exclusion" in lowered  # mentioned in Important note
        assert "verification" in lowered

    def test_prompt_includes_exclusion_example(self):
        """Prompt includes check_exclusions example JSON."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Exclusion check.")

        assert '"tool_name": "check_exclusions"' in prompt
        assert '"course_code": "CSC148H1"' in prompt

    def test_prompt_includes_verification_example(self):
        """Prompt includes get_course_metadata_status example JSON."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Verification check.")

        assert '"tool_name": "get_course_metadata_status"' in prompt
        assert "MAT137Y1" in prompt

    # -- clarification guidance -------------------------------------------

    def test_prompt_contains_clarify_action_guidance(self):
        """Prompt explains action='clarify' for missing information."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "What course should I take?")
        assert "clarify" in prompt.lower()
        assert "missing" in prompt.lower() or "enough information" in prompt.lower()

    def test_prompt_contains_vague_query_example(self):
        """Prompt shows clarification example for vague queries."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "What course?")
        assert '"action": "clarify"' in prompt
        assert "completed" in prompt.lower()
        assert "program" in prompt.lower()

    # -- requirement-tag mapping ------------------------------------------

    def test_prompt_maps_math_to_first_year_math_pathway(self):
        """Math requirement → first_year_math_pathway."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Math requirement?")
        assert "first_year_math_pathway" in prompt

    def test_prompt_maps_pool_to_computational_cognition(self):
        """Pool questions still map to computational_cognition_stream_pool."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Pool courses?")
        assert "computational_cognition_stream_pool" in prompt

    # -- MAT137 multi-step example ----------------------------------------

    def test_prompt_includes_mat137_multistep_example(self):
        """Prompt shows MAT137 verification + math pathway example."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Should I take MAT137Y1?")

        assert "MAT137Y1" in prompt
        assert "get_course_metadata_status" in prompt
        assert "first_year_math_pathway" in prompt

    def test_prompt_mat137_metadata_before_pathway(self):
        """MAT137 example shows metadata check BEFORE pathway query."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "MAT137?")

        meta_pos = prompt.find("get_course_metadata_status")
        pathway_pos = prompt.find("first_year_math_pathway")
        assert meta_pos < pathway_pos, (
            "Expected get_course_metadata_status before "
            "first_year_math_pathway in the example"
        )

    # -- preview inference + unsupported claims rules ---------------------

    def test_prompt_forbids_preview_inference(self):
        """Prompt forbids inferring absence from preview."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "MAT137?")

        assert "preview" in prompt.lower()
        assert "absent" in prompt.lower()

    def test_prompt_forbids_unsupported_requirement_claims(self):
        """Prompt forbids unsupported program-requirement claims."""
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Requirement?")

        assert "program requirement" in prompt.lower()
        assert "tool observation" in prompt.lower()

    # -- audit tool guidance ----------------------------------------------

    def test_prompt_maps_audit_to_audit_tool(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "What requirements have I completed?")
        assert "audit_program_progress" in prompt.lower()

    def test_prompt_prereq_still_maps_to_check_prerequisites(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC384H1?")
        assert "check_prerequisites" in prompt.lower()

    def test_prompt_missing_courses_for_audit_triggers_clarify(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "What progress have I made?")
        assert "clarify" in prompt.lower()
        assert "completed" in prompt.lower()

    # -- prior-steps context ----------------------------------------------

    def test_prior_steps_context_includes_step_info(self):
        """When prior_steps exist, context shows tool name, args, observation."""
        agent = CoursePlanningAgent(
            completed_courses=["CSC148H1"],
            model=_SpyModel(),
        )
        prior = [{
            "thought": "Check prerequisites.",
            "tool_called": "check_prerequisites",
            "arguments": {"course_code": "CSC384H1",
                          "completed_courses": ["CSC148H1"]},
            "observation": "not_eligible.",
        }]
        agent._reason_about_request(
            "Can I take CSC384H1?", prior_steps=prior
        )

        # Find the prior-steps context system message.
        prior_msg = ""
        for msg in agent.model.last_messages:
            if msg["role"] == "system" and "Completed tool steps" in msg["content"]:
                prior_msg = msg["content"]
                break

        assert "check_prerequisites" in prior_msg
        assert "CSC384H1" in prior_msg
        assert "CSC148H1" in prior_msg
        assert "not_eligible" in prior_msg

    def test_prior_steps_context_warns_no_repeat(self):
        """Prior-steps context tells model not to repeat identical calls."""
        agent = CoursePlanningAgent(
            completed_courses=["CSC148H1"],
            model=_SpyModel(),
        )
        prior = [{
            "thought": "...",
            "tool_called": "check_prerequisites",
            "arguments": {"course_code": "CSC384H1",
                          "completed_courses": ["CSC148H1"]},
            "observation": "not_eligible.",
        }]
        agent._reason_about_request(
            "Can I take CSC384H1?", prior_steps=prior
        )

        prior_msg = ""
        for msg in agent.model.last_messages:
            if msg["role"] == "system" and "Completed tool steps" in msg["content"]:
                prior_msg = msg["content"]
                break

        assert "Do NOT repeat" in prior_msg or "do not repeat" in prior_msg.lower()

    def test_prior_steps_context_tells_model_to_identify_unanswered(self):
        """Prior-steps context asks model to identify unanswered parts."""
        agent = CoursePlanningAgent(
            completed_courses=["CSC148H1"],
            model=_SpyModel(),
        )
        prior = [{
            "thought": "...",
            "tool_called": "check_prerequisites",
            "arguments": {"course_code": "CSC384H1",
                          "completed_courses": ["CSC148H1"]},
            "observation": "not_eligible.",
        }]
        agent._reason_about_request(
            "Can I take CSC384H1?", prior_steps=prior
        )

        prior_msg = ""
        for msg in agent.model.last_messages:
            if msg["role"] == "system" and "Completed tool steps" in msg["content"]:
                prior_msg = msg["content"]
                break

        assert "unanswered" in prior_msg.lower()


# ---------------------------------------------------------------------------
# structured tool action parser
# ---------------------------------------------------------------------------

def test_parse_valid_recommendation_action():
    """Valid recommendation action parses correctly."""
    response = (
        'I will recommend courses. '
        '{"tool_name": "recommend_courses_for_requirement", '
        '"arguments": {"requirement_tag": "computational_cognition_stream_pool", '
        '"completed_courses": ["COG100H1"]}}'
    )
    result = parse_tool_action(response)
    assert result["valid"] is True
    assert result["tool_name"] == "recommend_courses_for_requirement"
    assert result["arguments"]["requirement_tag"] == (
        "computational_cognition_stream_pool"
    )
    assert result["error"] is None


def test_parse_valid_prerequisite_action():
    """Valid prerequisite check action parses correctly."""
    response = (
        '{"tool_name": "check_prerequisites", '
        '"arguments": {"course_code": "CSC384H1", '
        '"completed_courses": ["CSC148H1"]}}'
    )
    result = parse_tool_action(response)
    assert result["valid"] is True
    assert result["tool_name"] == "check_prerequisites"
    assert result["arguments"]["course_code"] == "CSC384H1"


def test_parse_invalid_tool_name():
    """Unknown tool name returns valid=False with error."""
    response = (
        '{"tool_name": "nonexistent_tool", '
        '"arguments": {"course_code": "CSC108H1"}}'
    )
    result = parse_tool_action(response)
    assert result["valid"] is False
    assert result["tool_name"] == "nonexistent_tool"
    assert "Unknown tool" in result["error"]


def test_parse_missing_required_arguments():
    """Missing required argument returns valid=False with error."""
    response = (
        '{"tool_name": "check_prerequisites", '
        '"arguments": {"course_code": "CSC384H1"}}'
    )
    result = parse_tool_action(response)
    assert result["valid"] is False
    assert result["tool_name"] == "check_prerequisites"
    assert "Missing required arguments" in result["error"]


def test_parse_malformed_response():
    """Unparseable response returns valid=False."""
    result = parse_tool_action("This is just plain text, no JSON at all.")
    assert result["valid"] is False
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# parser — markdown code block (Format C)
# ---------------------------------------------------------------------------

def test_parse_markdown_code_block():
    """JSON inside a ```json code block parses correctly."""
    response = (
        "I should check the course prerequisites.\n\n"
        "```json\n"
        "{\n"
        '  "tool_name": "check_prerequisites",\n'
        '  "arguments": {\n'
        '    "course_code": "CSC384H1",\n'
        '    "completed_courses": ["CSC148H1"]\n'
        "  }\n"
        "}\n"
        "```"
    )
    result = parse_tool_action(response)
    assert result["valid"] is True
    assert result["tool_name"] == "check_prerequisites"
    assert result["arguments"]["course_code"] == "CSC384H1"


# ---------------------------------------------------------------------------
# parser — JSON with surrounding text (Format B)
# ---------------------------------------------------------------------------

def test_parse_json_with_surrounding_text():
    """JSON after an explanation sentence still parses."""
    response = (
        "I should look up the course details first.\n\n"
        '{"tool_name": "get_course_details", '
        '"arguments": {"course_code": "CSC108H1"}}'
    )
    result = parse_tool_action(response)
    assert result["valid"] is True
    assert result["tool_name"] == "get_course_details"


def test_parse_with_optional_interests():
    """Parser accepts optional interests argument without error."""
    response = (
        '{"tool_name": "recommend_courses_for_requirement", '
        '"arguments": {"requirement_tag": "computational_cognition_stream_pool", '
        '"completed_courses": ["CSC108H1"], '
        '"interests": ["AI", "machine learning"]}}'
    )
    result = parse_tool_action(response)
    assert result["valid"] is True
    assert result["tool_name"] == "recommend_courses_for_requirement"
    assert result["arguments"]["interests"] == ["AI", "machine learning"]


# ---------------------------------------------------------------------------
# parser — clarify action
# ---------------------------------------------------------------------------


class TestParseClarifyAction:
    """Verify action='clarify' parsing."""

    def test_valid_clarify_parses(self):
        result = parse_tool_action(
            '{"action": "clarify", '
            '"question": "Which courses have you completed?"}'
        )
        assert result["action"] == "clarify"
        assert result["valid"] is True
        assert result["tool_name"] is None
        assert result["question"] == "Which courses have you completed?"

    def test_missing_question_rejected(self):
        result = parse_tool_action('{"action": "clarify"}')
        assert result["action"] == "clarify"
        assert result["valid"] is False
        assert "question" in result["error"].lower()

    def test_blank_question_rejected(self):
        result = parse_tool_action(
            '{"action": "clarify", "question": "   "}'
        )
        assert result["action"] == "clarify"
        assert result["valid"] is False
        assert "question" in result["error"].lower()

    def test_tool_action_still_works(self):
        """Existing tool action unchanged by clarify addition."""
        result = parse_tool_action(
            '{"tool_name": "check_prerequisites", '
            '"arguments": {"course_code": "CSC384H1", '
            '"completed_courses": ["CSC148H1"]}}'
        )
        assert result["action"] == "tool"
        assert result["valid"] is True

    def test_finish_action_still_works(self):
        """Existing finish action unchanged."""
        result = parse_tool_action('{"action": "finish"}')
        assert result["action"] == "finish"
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# ReAct loop — tool calling with parsed arguments
# ---------------------------------------------------------------------------

def test_agent_returns_observation_after_tool():
    """_call_tool with valid args returns an observation string."""
    agent = CoursePlanningAgent()
    observation = agent._call_tool(
        "recommend_courses_for_requirement",
        {
            "requirement_tag": "computational_cognition_stream_pool",
            "completed_courses": [],
        },
    )
    assert isinstance(observation, str)
    assert len(observation) > 0
    assert "computational_cognition_stream_pool" in observation


# ---------------------------------------------------------------------------
# Observation formatting — recommend_courses_for_requirement
# ---------------------------------------------------------------------------


class TestRecommendationObservation:
    """Verify the observation string produced for recommendation results."""

    PREVIEW_LIMIT = 10

    @staticmethod
    def _get_observation(
        tag: str = "computational_cognition_stream_pool",
        completed: list[str] | None = None,
    ) -> str:
        """Call the tool through the agent and return the observation."""
        agent = CoursePlanningAgent(completed or [])
        return agent._call_tool(
            "recommend_courses_for_requirement",
            {"requirement_tag": tag, "completed_courses": completed or []},
        )

    # -- content checks --------------------------------------------------

    def test_includes_total_course_count(self):
        """Observation states the total number of courses found."""
        observation = self._get_observation()
        assert "65 courses" in observation

        total = _format_recommendation_observation(
            [{"course_code": "TEST101H1"}], "test_tag"
        )
        assert "1 courses" in total

    def test_includes_course_codes(self):
        """Observation preview includes specific course codes."""
        observation = self._get_observation()
        # Courses that appear in the first 10 of the stream pool.
        assert "CSC165H1" in observation
        assert "COG260H1" in observation

    def test_includes_prerequisite_status(self):
        """Observation includes prerequisite_status for preview courses."""
        observation = self._get_observation()
        assert "Prerequisites:" in observation

    def test_includes_breadth(self):
        """Observation includes breadth_name for preview courses."""
        observation = self._get_observation()
        assert "Breadth:" in observation

    def test_includes_department_and_level(self):
        """Observation includes department and level for preview courses."""
        observation = self._get_observation()
        assert "Department:" in observation
        assert "Level:" in observation

    def test_includes_verification_status(self):
        """Observation includes verification_status for preview courses."""
        observation = self._get_observation()
        assert "Verification:" in observation

    # -- capping ----------------------------------------------------------

    def test_observation_is_capped_at_10(self):
        """Preview lists at most 10 courses, not all 65."""
        observation = self._get_observation()
        # The preview says "Preview (10 of 65)" or similar
        assert "10 of 65" in observation

    def test_does_not_include_all_courses(self):
        """Observation does not dump the full 65-course list."""
        observation = self._get_observation()
        # After 10 preview items, the 11th should not appear as "11."
        assert "\n11. " not in observation
        # And no "12." prefix either
        assert "\n12. " not in observation

    # -- empty result -----------------------------------------------------

    def test_empty_result_returns_clear_message(self):
        """Observations says no courses found for an unknown tag."""
        observation = self._get_observation(tag="nonexistent_tag")
        assert "No courses found" in observation
        assert "nonexistent_tag" in observation

    # -- other tools unchanged --------------------------------------------

    def test_get_course_details_observation_unchanged(self):
        """get_course_details still returns its original format."""
        agent = CoursePlanningAgent()
        obs = agent._call_tool(
            "get_course_details", {"course_code": "CSC108H1"}
        )
        assert "Found course:" in obs
        assert "CSC108H1" in obs

    def test_check_prerequisites_observation_unchanged(self):
        """check_prerequisites still returns its original format."""
        agent = CoursePlanningAgent(["CSC148H1"])
        obs = agent._call_tool(
            "check_prerequisites",
            {"course_code": "CSC384H1", "completed_courses": ["CSC148H1"]},
        )
        assert "Prerequisite check for" in obs
        assert "CSC384H1" in obs

    # -- interest fields in observation ---------------------------------

    def test_observation_includes_matched_interests(self):
        """Observation shows interest_match when courses have the field."""
        agent = CoursePlanningAgent()
        obs = agent._call_tool(
            "recommend_courses_for_requirement",
            {
                "requirement_tag": "computational_cognition_stream_pool",
                "completed_courses": [],
                "interests": ["AI", "machine learning"],
            },
        )
        assert "Interest match:" in obs


# ---------------------------------------------------------------------------
# ReAct loop — final output
# ---------------------------------------------------------------------------

def test_agent_final_output_contains_final_answer():
    """handle_request() returns a dict with final_answer (graceful fallback)."""
    agent = CoursePlanningAgent(["COG100H1"])
    result = agent.handle_request("I want to take AI courses")
    assert "final_answer" in result
    assert isinstance(result["final_answer"], str)
    assert len(result["final_answer"]) > 0


def test_agent_output_has_all_react_keys():
    """handle_request() returns thought, tool_called, observation, final_answer."""
    agent = CoursePlanningAgent(["COG100H1"])
    result = agent.handle_request("Recommend AI courses")
    for key in ("thought", "tool_called", "observation", "final_answer"):
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Data safety
# ---------------------------------------------------------------------------

def test_agent_does_not_modify_catalog():
    """Handling a request must not mutate the course catalog."""
    from src.tools import load_courses

    before = load_courses()
    agent = CoursePlanningAgent(["COG100H1"])
    agent.handle_request("I am interested in AI courses")
    after = load_courses()

    assert before == after


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_missing_skill_file_raises_error():
    """load_course_planning_skill raises FileNotFoundError for bad path."""
    import src.agent as agent_module

    original = agent_module._PROJECT_ROOT
    try:
        agent_module._PROJECT_ROOT = Path("/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            load_course_planning_skill()
    finally:
        agent_module._PROJECT_ROOT = original


# =========================================================================
# Sequence model — returns pre-set responses in order, for multi-step tests
# =========================================================================


class _SequenceModel(BaseModelInterface):
    """Returns pre-set responses in order.  Raises if exhausted."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[list[dict]] = []
        self.idx = 0

    def generate_response(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if self.idx >= len(self.responses):
            raise RuntimeError(
                f"SequenceModel exhausted at index {self.idx}"
            )
        response = self.responses[self.idx]
        self.idx += 1
        return response


# =========================================================================
# parse_tool_action — action field support
# =========================================================================


class TestParseActionField:
    """Verify action="tool"|"finish"|legacy parsing."""

    def test_legacy_tool_without_action_is_valid(self):
        """Legacy JSON without 'action' field is treated as action='tool'."""
        result = parse_tool_action(
            '{"tool_name": "check_prerequisites", '
            '"arguments": {"course_code": "CSC384H1", '
            '"completed_courses": ["CSC148H1"]}}'
        )
        assert result["action"] == "tool"
        assert result["valid"] is True
        assert result["tool_name"] == "check_prerequisites"

    def test_explicit_tool_action_is_valid(self):
        """Explicit action='tool' parses correctly."""
        result = parse_tool_action(
            '{"action": "tool", '
            '"tool_name": "get_course_details", '
            '"arguments": {"course_code": "CSC108H1"}}'
        )
        assert result["action"] == "tool"
        assert result["valid"] is True
        assert result["tool_name"] == "get_course_details"

    def test_explicit_finish_action_is_valid(self):
        """Explicit action='finish' parses as valid finish."""
        result = parse_tool_action('{"action": "finish"}')
        assert result["action"] == "finish"
        assert result["valid"] is True
        assert result["tool_name"] is None

    def test_malformed_action_still_invalid(self):
        """Malformed JSON still returns invalid."""
        result = parse_tool_action("not json at all")
        assert result["action"] is None
        assert result["valid"] is False

    def test_unknown_action_type_is_invalid(self):
        """Unknown action type returns invalid."""
        result = parse_tool_action(
            '{"action": "unknown_thing", "tool_name": "x"}'
        )
        assert result["action"] is None
        assert result["valid"] is False


# =========================================================================
# handle_request — multi-step ReAct loop
# =========================================================================


class TestMultiStepReAct:
    """Verify the bounded multi-step ReAct loop behavior."""

    # -- single-step backward compatibility -------------------------------

    def test_one_step_with_legacy_json(self):
        """One legacy tool call produces one step (max_tool_steps=1)."""
        agent = CoursePlanningAgent(
            completed_courses=["CSC148H1"],
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "Final answer with eligibility information.",
            ]),
        )
        result = agent.handle_request(
            "Can I take CSC384H1?", max_tool_steps=1
        )

        assert len(result["steps"]) == 1
        assert result["steps"][0]["tool_called"] == "check_prerequisites"
        assert result["stop_reason"] == "max_steps"
        assert result["thought"] == result["steps"][0]["thought"]
        assert result["tool_called"] == "check_prerequisites"
        assert result["final_answer"] == "Final answer with eligibility information."

    def test_one_step_with_explicit_tool(self):
        """Explicit action='tool' produces one step (max_tool_steps=1)."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "tool", '
                '"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                "Final answer with course details.",
            ]),
        )
        result = agent.handle_request(
            "Tell me about CSC108H1.", max_tool_steps=1
        )
        assert len(result["steps"]) == 1
        assert result["steps"][0]["tool_called"] == "get_course_details"

    # -- multi-step accumulation ------------------------------------------

    def test_two_different_tools_accumulate_two_steps(self):
        """Two different tool calls produce two steps."""
        agent = CoursePlanningAgent(
            completed_courses=["CSC148H1", "STA237H1"],
            model=_SequenceModel([
                # Step 1: check prerequisites for CSC384H1.
                '{"action": "tool", '
                '"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1", "STA237H1"]}}',
                # Step 2: check term availability.
                '{"action": "tool", '
                '"tool_name": "check_term_availability", '
                '"arguments": {"course_code": "CSC384H1", '
                '"target_term": "Winter"}}',
                # Final answer.
                "CSC384H1 is offered in Winter. You may be eligible.",
            ]),
        )
        result = agent.handle_request(
            "Can I take CSC384H1 in Winter with CSC148H1 and STA237H1?",
            max_tool_steps=2,
        )
        assert len(result["steps"]) == 2
        assert result["steps"][0]["tool_called"] == "check_prerequisites"
        assert result["steps"][1]["tool_called"] == "check_term_availability"
        assert result["stop_reason"] == "max_steps"

    def test_step_includes_all_keys(self):
        """Each step dict has thought, tool_called, arguments, observation."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                "Done.",
            ]),
        )
        result = agent.handle_request("What is CSC108H1?", max_tool_steps=1)
        step = result["steps"][0]
        for key in ("thought", "tool_called", "arguments", "observation"):
            assert key in step, f"Missing key: {key}"
        assert step["arguments"] == {"course_code": "CSC108H1"}
        assert "observation" in step

    # -- finish action ----------------------------------------------------

    def test_explicit_finish_stops_before_max_steps(self):
        """action='finish' stops the loop even when max_tool_steps remain."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "tool", '
                '"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                '{"action": "finish"}',
                "Comprehensive final answer.",
            ]),
        )
        result = agent.handle_request("Tell me about CSC108H1.", max_tool_steps=5)
        assert len(result["steps"]) == 1
        assert result["stop_reason"] == "finish"

    # -- max_tool_steps enforcement ---------------------------------------

    def test_max_tool_steps_respected(self):
        """Loop stops at max_tool_steps even with more valid tool responses."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC384H1"}}',
                "Final synthesis.",
            ]),
        )
        result = agent.handle_request(
            "Check CSC384H1.", max_tool_steps=1
        )
        assert len(result["steps"]) == 1
        assert result["stop_reason"] == "max_steps"

    def test_max_tool_steps_zero_runs_zero_tools(self):
        """max_tool_steps=0 means no tools are called at all."""
        agent = CoursePlanningAgent(
            model=_SequenceModel(["No tools were called."]),
        )
        result = agent.handle_request("Query.", max_tool_steps=0)
        assert result["steps"] == []
        assert result["stop_reason"] == "max_steps"
        # No tool call → the model wasn't asked for one.
        # Actually, the loop runs 0 times, so no reasoning call happens.
        # The fallback final_answer is used.
        assert "could not determine" in result["final_answer"].lower()

    # -- repeated action guard --------------------------------------------

    def test_repeated_identical_tool_stops(self):
        """Identical tool+arguments on second call stops with repeated_action."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                # Identical call — should be caught.
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "Final after repeat guard.",
            ]),
        )
        result = agent.handle_request(
            "Check CSC384H1.", max_tool_steps=3
        )
        assert len(result["steps"]) == 1
        assert result["stop_reason"] == "repeated_action"

    def test_different_args_same_tool_is_not_repeated(self):
        """Same tool with different arguments is NOT a repeat."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC311H1", '
                '"completed_courses": ["CSC148H1", "STA237H1"]}}',
                "Final.",
            ]),
        )
        result = agent.handle_request(
            "Check two courses.", max_tool_steps=2
        )
        assert len(result["steps"]) == 2

    # -- parse error handling ---------------------------------------------

    def test_parse_error_after_success_generates_answer(self):
        """Parse error after one successful step still uses that observation."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                "not valid json at all",
                "Final from the one good result.",
            ]),
        )
        result = agent.handle_request(
            "Tell me about CSC108H1.", max_tool_steps=2
        )
        # One step succeeded, then parse error.
        assert len(result["steps"]) == 1
        assert result["stop_reason"] == "parse_error"
        # Final answer was generated from the successful step.
        assert "one good result" in result["final_answer"]

    def test_no_action_returned_on_first_call(self):
        """When the first model response has no parseable JSON."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                "Just some text, no JSON at all.",
                "Fallback answer.",
            ]),
        )
        result = agent.handle_request("Query?", max_tool_steps=2)
        assert result["steps"] == []
        assert result["stop_reason"] == "no_action"
        assert "could not determine" in result["final_answer"].lower()

    # -- stop_reason and steps in result ----------------------------------

    def test_result_includes_steps_and_stop_reason(self):
        """Result dict has 'steps' list and 'stop_reason' string."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                '{"action": "finish"}',
                "Done.",
            ]),
        )
        result = agent.handle_request("Query.", max_tool_steps=3)
        assert isinstance(result["steps"], list)
        assert result["stop_reason"] in (
            "finish", "max_steps", "parse_error",
            "repeated_action", "no_action",
        )

    # -- prior observation forwarding -------------------------------------

    def test_prior_observation_in_second_reasoning_call(self):
        """Step 2's reasoning messages include step 1's observation."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                '{"action": "tool", '
                '"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC384H1"}}',
                "Final answer.",
            ]),
        )
        agent.handle_request("Check CSC384H1.", max_tool_steps=2)

        # Second reasoning call (index 2 in calls: 0=reason1, 1=answer1, 2=reason2)
        # Actually: _reason_about_request → _generate_answer sequence:
        # call 0: _reason_about_request (step 1)
        # call 1: _generate_answer (step 1) — No wait, _generate_answer only called once at the END
        # Let me think about this again...
        # _reason_about_request gets called for step 1 and step 2
        # _generate_answer gets called once at the end
        # So calls:
        # 0: _reason_about_request (step 1)
        # 1: _reason_about_request (step 2) — should contain step 1 observation
        # 2: _generate_answer
        assert len(agent.model.calls) >= 2, (
            f"Expected at least 2 calls, got {len(agent.model.calls)}"
        )

        # The second reasoning call (index 1) should contain the observation
        # from step 1.
        second_call_messages = agent.model.calls[1]
        combined = " ".join(
            m["content"] for m in second_call_messages
        )
        # Step 1 observation should be present (prerequisite status).
        assert "not_eligible" in combined.lower() or \
               "eligible" in combined.lower() or \
               "manual_review" in combined.lower(), (
            "Prior observation not found in second reasoning call messages"
        )

    # -- final answer includes all observations ---------------------------

    def test_final_answer_messages_contain_all_observations(self):
        """The final _generate_answer call includes all step observations."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC384H1"}}',
                "Synthesised final answer.",
            ]),
        )
        agent.handle_request("Check CSC384H1.", max_tool_steps=2)

        # The last call is _generate_answer.
        final_messages = agent.model.calls[-1]
        combined = " ".join(
            m["content"] for m in final_messages
        )
        # Both observations should be referenced.
        assert "check_prerequisites" in combined.lower()
        assert "get_course_details" in combined.lower()

    # -- generate_answer prompt content -----------------------------------

    def test_generate_answer_prompt_separates_statuses(self):
        """Prompt tells model to separate prerequisite and metadata statuses."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "MAT137Y1", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        # The last call is _generate_answer.
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "attribute every status" in lowered
        assert "do not attach" in lowered or "do not combine" in lowered

    def test_generate_answer_prompt_distinguishes_dimensions(self):
        """Prompt distinguishes eligibility, verification, term, pathway."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        for term in ["prerequisite eligibility", "metadata verification",
                     "term availability", "program-pathway membership"]:
            assert term in lowered, f"Missing: {term}"

    def test_generate_answer_prompt_uses_listed_as_option_wording(self):
        """Prompt says 'listed as an option' not 'recommended'."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "recommend_courses_for_requirement", '
                '"arguments": {"requirement_tag": "first_year_math_pathway", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "listed as an option" in lowered
        assert "do not automatically say" in lowered

    def test_generate_answer_prompt_forbids_auto_recommended(self):
        """Prompt prohibits automatically saying 'recommended'."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_metadata_status", '
                '"arguments": {"course_code": "MAT137Y1"}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "do not automatically say" in lowered
        assert '"recommended"' in lowered
        assert '"should take"' in lowered

    # -- pathway alternatives guidance ------------------------------------

    def test_generate_answer_prompt_asks_for_alternatives(self):
        """Prompt asks for useful alternatives from pathway observations."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "recommend_courses_for_requirement", '
                '"arguments": {"requirement_tag": "first_year_math_pathway", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "other options" in lowered
        assert "alternatives" in lowered
        assert "retrieved" in lowered

    def test_generate_answer_prompt_limits_alternatives_to_three(self):
        """Alternatives are limited to at most three."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_metadata_status", '
                '"arguments": {"course_code": "MAT137Y1"}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "at most three" in lowered

    def test_generate_answer_prompt_alternatives_not_auto_recommended(self):
        """Alternatives are 'listed options', not automatic recommendations."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "recommend_courses_for_requirement", '
                '"arguments": {"requirement_tag": "first_year_math_pathway", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "not automatic recommendations" in lowered
        assert '"better"' in lowered
        assert '"definitely available"' in lowered

    def test_generate_answer_prompt_preserves_alternative_statuses(self):
        """Prompt requires preserving verification and term statuses."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "do not remove or soften" in lowered
        assert "needs_official_verification" in lowered
        assert "unknown" in lowered

    def test_generate_answer_prompt_evidence_attribution_still_present(self):
        """The original evidence-attribution guidance is preserved."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": []}}',
                "Final.",
            ]),
        )
        agent.handle_request("Q?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "attribute every status" in lowered
        assert "program-pathway membership" in lowered

    # -- generate_answer audit guidance -----------------------------------

    def test_generate_answer_prompt_includes_audit_guidance(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": ["COG100H1"]}}',
                "Audit summary.",
            ]),
        )
        agent.handle_request("Audit my progress.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "audit_program_progress" in lowered or "audit" in lowered

    def test_generate_answer_prompt_forbids_credit_recalculation(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit result.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "do not recalculate" in lowered

    def test_generate_answer_prompt_includes_degree_explorer_disclaimer(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "degree explorer" in lowered or "not an official" in lowered

    # -- audit tool through agent loop ------------------------------------

    def test_audit_tool_call_succeeds(self):
        agent = CoursePlanningAgent(
            completed_courses=["COG100H1", "CSC108H1", "CSC148H1"],
            model=_SequenceModel([
                '{"action": "tool", '
                '"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": ["COG100H1", '
                '"CSC108H1", "CSC148H1"]}}',
                "Your audit shows first-year requirements completed.",
            ]),
        )
        result = agent.handle_request(
            "What requirements have I completed?", max_tool_steps=1,
        )
        assert result["tool_called"] == "audit_program_progress"
        assert len(result["steps"]) == 1
        assert "requirement" in result["observation"].lower()

    def test_audit_tool_in_steps(self):
        agent = CoursePlanningAgent(
            completed_courses=["COG100H1"],
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": ["COG100H1"]}}',
                "Audit summary.",
            ]),
        )
        result = agent.handle_request("What progress?", max_tool_steps=1)
        assert result["steps"][0]["tool_called"] == "audit_program_progress"

    # -- observation formatting -------------------------------------------

    def test_audit_observation_includes_exclusion_reason(self):
        agent = CoursePlanningAgent(
            completed_courses=["CSC108H1", "CSC148H1"],
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": ["CSC108H1", '
                '"CSC148H1"]}}',
                "Audit.",
            ]),
        )
        result = agent.handle_request("Audit.", max_tool_steps=1)
        obs = result["steps"][0]["observation"]
        assert "exclusion" in obs.lower()

    def test_audit_observation_includes_ambiguity_reason(self):
        agent = CoursePlanningAgent(
            completed_courses=["MAT135H1", "MAT136H1"],
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": ["MAT135H1", '
                '"MAT136H1"]}}',
                "Audit.",
            ]),
        )
        result = agent.handle_request("Audit.", max_tool_steps=1)
        obs = result["steps"][0]["observation"]
        assert "ambiguity" in obs.lower()

    def test_capstone_not_manual_review_in_observation(self):
        agent = CoursePlanningAgent(
            completed_courses=[],
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        result = agent.handle_request("Audit.", max_tool_steps=1)
        obs = result["steps"][0]["observation"]
        # Capstone line should show review=clear, not manual_review_needed.
        capstone_lines = [l for l in obs.split("\n")
                          if "fourth_year_capstone" in l]
        if capstone_lines:
            assert "review=clear" in capstone_lines[0]

    def test_priority_observation_includes_category(self):
        agent = CoursePlanningAgent(
            completed_courses=["COG100H1"],
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": ["COG100H1"]}}',
                "Audit.",
            ]),
        )
        result = agent.handle_request("Audit.", max_tool_steps=1)
        obs = result["steps"][0]["observation"]
        # Priority items should include the category name.
        assert "first_year_required" in obs or "second_year" in obs

    # -- answer prompt anti-conflation ------------------------------------

    def test_answer_prompt_forbids_conflating_warning_types(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "do not describe an exclusion conflict" in lowered
        assert "do not describe an ambiguous expression" in lowered

    def test_answer_prompt_forbids_assuming_mutual_exclusion(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "do not assume it is mutual" in lowered
        assert "exclude each other" in lowered
        assert '"mutual exclusion"' in lowered

    def test_answer_prompt_distinguishes_one_direction_exclusion(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "lists" in lowered and "as an exclusion" in lowered

    def test_answer_prompt_provisional_completion_wording(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "provisionally completed" in lowered
        assert "requires review" in lowered

    def test_answer_prompt_forbids_definitive_completion_with_review(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "audit_program_progress", '
                '"arguments": {"completed_courses": []}}',
                "Audit.",
            ]),
        )
        agent.handle_request("Audit.", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "do not claim" in lowered
        assert "completed all" in lowered

    # -- retake / exclusion guidance -------------------------------------

    def test_answer_prompt_forbids_generic_retake_claims(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_exclusions", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "Exclusion found.",
            ]),
        )
        agent.handle_request("Can I retake CSC108H1?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "cannot determine" in lowered or "cannot determine whether" in lowered
        # Prompt forbids generic retake claims (listed as anti-examples).
        assert "do not" in lowered
        assert "unsupported generalizations" in lowered

    def test_answer_prompt_forbids_retake_permission_without_evidence(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_exclusions", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": []}}',
                "Exclusion.",
            ]),
        )
        agent.handle_request("Retake?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        # Prompt explicitly lists these as forbidden wording.
        assert '"you can retake' in lowered  # listed as anti-example
        assert '"you cannot retake' in lowered  # listed as anti-example
        assert "do not" in lowered

    def test_answer_prompt_forbids_claiming_no_credit_without_evidence(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_exclusions", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": []}}',
                "Exclusion.",
            ]),
        )
        agent.handle_request("Retake?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        # Prompt lists these as examples of over-strengthening to avoid.
        assert "no additional credit" in lowered  # anti-example
        assert "will not count" in lowered  # anti-example
        assert "do not strengthen" in lowered

    def test_answer_prompt_requires_may_affect_wording(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_exclusions", '
                '"arguments": {"course_code": "CSC108H1", '
                '"completed_courses": []}}',
                "Exclusion.",
            ]),
        )
        agent.handle_request("Retake?", max_tool_steps=1)
        system_msg = ""
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                system_msg = m["content"]
                break
        lowered = system_msg.lower()
        assert "may be affected" in lowered or "may affect" in lowered

    # -- backward compatible flat keys ------------------------------------

    def test_flat_keys_reflect_first_successful_step(self):
        """thought/tool_called/observation point to step[0]."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": []}}',
                "Done.",
            ]),
        )
        result = agent.handle_request("Tell me stuff.", max_tool_steps=2)

        assert result["thought"] == result["steps"][0]["thought"]
        assert result["tool_called"] == "get_course_details"
        assert result["observation"] == result["steps"][0]["observation"]
        assert result["final_answer"] == "Done."

    def test_flat_keys_with_no_steps_are_fallback(self):
        """When no steps succeed, flat keys contain fallback values."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                "Not valid JSON.",
                "Fallback.",
            ]),
        )
        result = agent.handle_request("Query?", max_tool_steps=2)
        assert result["tool_called"] is None
        assert len(result["thought"]) > 0
        assert result["steps"] == []
        assert result["stop_reason"] == "no_action"


# =========================================================================
# Clarify action — loop behavior
# =========================================================================


class TestClarifyLoop:
    """Verify handle_request behavior for action='clarify'."""

    def test_clarify_stops_immediately(self):
        """clarify action stops the loop at step 1."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "Which courses have you completed?"}',
            ]),
        )
        result = agent.handle_request("What should I take?")
        assert result["stop_reason"] == "clarify"

    def test_clarify_no_tool_called(self):
        """No tool is executed for clarify."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "What is your program?"}',
            ]),
        )
        result = agent.handle_request("Help me plan.")
        assert result["tool_called"] is None
        assert result["steps"] == []

    def test_clarify_final_answer_is_question(self):
        """final_answer is the clarification question."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "What term are you planning for?"}',
            ]),
        )
        result = agent.handle_request("Plan my courses.")
        assert result["final_answer"] == "What term are you planning for?"

    def test_clarify_observation_is_placeholder(self):
        """observation is a placeholder string."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "Which courses completed?"}',
            ]),
        )
        result = agent.handle_request("Q?")
        assert result["observation"] == "Clarification required."

    def test_clarify_last_model_response_preserved(self):
        """last_model_response is the clarify JSON."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "What have you taken?"}',
            ]),
        )
        result = agent.handle_request("Q?")
        assert result["last_model_response"] is not None
        assert "clarify" in result["last_model_response"]

    def test_clarify_parse_error_is_none(self):
        """parse_error is None for valid clarify (not a parse error)."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "Your completed courses?"}',
            ]),
        )
        result = agent.handle_request("Q?")
        assert result["parse_error"] is None

    def test_clarify_generate_answer_not_called(self):
        """_generate_answer is NOT called for clarify (no model call)."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "What is your target term?"}',
            ]),
        )
        result = agent.handle_request("Plan please.")
        # Model was only called once (for _reason_about_request).
        # _generate_answer would be a 2nd call — not reached for clarify.
        assert result["final_answer"] == "What is your target term?"
        # The SequenceModel had 1 response and it was consumed by reasoning.
        # If _generate_answer was called, it would exhaust and raise.

    def test_clarify_not_confused_with_finish(self):
        """clarify and finish are distinct stop reasons."""
        agent_finish = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                '{"action": "finish"}',
                "Final answer.",
            ]),
        )
        r_finish = agent_finish.handle_request("Q?", max_tool_steps=2)
        assert r_finish["stop_reason"] == "finish"
        assert r_finish["steps"] != []

        agent_clarify = CoursePlanningAgent(
            model=_SequenceModel([
                '{"action": "clarify", '
                '"question": "What courses?"}',
            ]),
        )
        r_clarify = agent_clarify.handle_request("Q?")
        assert r_clarify["stop_reason"] == "clarify"
        assert r_clarify["steps"] == []


# =========================================================================
# Diagnostic fields — last_model_response and parse_error
# =========================================================================


# =========================================================================
# Clarify for missing completed courses — prompt guidance
# =========================================================================


class TestClarifyMissingCoursesPrompt:
    """Verify prompt contains clarify-for-missing-courses guidance."""

    @staticmethod
    def _get_system_prompt(agent: CoursePlanningAgent, request: str) -> str:
        spy = _SpyModel()
        agent.model = spy
        agent._reason_about_request(request)
        for msg in spy.last_messages:
            if msg["role"] == "system":
                return msg["content"]
        return ""

    def test_rule_10_forbids_empty_completed_courses(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC311H1?")
        lowered = prompt.lower()
        assert "do not call check_prerequisites" in lowered.lower() or \
               "not call check_prerequisites" in lowered
        assert "empty" in lowered or "invented" in lowered

    def test_prompt_has_eligibility_clarify_example(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Am I eligible?")
        assert "Am I eligible for CSC311H1" in prompt
        assert '"action": "clarify"' in prompt

    def test_normal_prereq_check_still_works(self):
        """When completed_courses ARE provided, check_prerequisites is used."""
        agent = CoursePlanningAgent(
            completed_courses=["CSC148H1"],
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "Final answer.",
            ]),
        )
        result = agent.handle_request(
            "Can I take CSC384H1? I completed CSC148H1.",
            max_tool_steps=1,
        )
        assert result["tool_called"] == "check_prerequisites"
        assert result["stop_reason"] == "max_steps"


# =========================================================================
# Multi-step + grounding regression tests
# =========================================================================


class TestMultiStepGrounding:
    """Verify prompt rules for multi-step completeness and grounding."""

    @staticmethod
    def _get_system_prompt(agent: CoursePlanningAgent, request: str) -> str:
        spy = _SpyModel()
        agent.model = spy
        agent._reason_about_request(request)
        for msg in spy.last_messages:
            if msg["role"] == "system":
                return msg["content"]
        return ""

    @staticmethod
    def _get_answer_prompt(agent: CoursePlanningAgent) -> str:
        """Get the answer-generation system prompt."""
        agent.handle_request("Q?", max_tool_steps=1)
        for m in agent.model.calls[-1]:
            if m["role"] == "system":
                return m["content"]
        return ""

    # A. Both prerequisites + term must be checked.

    def test_prompt_requires_both_prereq_and_term(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC384H1 in Winter?")
        lowered = prompt.lower()
        assert "check_prerequisites" in lowered
        assert "check_term_availability" in lowered
        assert "do not skip" in lowered

    def test_prompt_says_check_term_even_if_not_eligible(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "Can I take CSC384H1 in Winter?")
        lowered = prompt.lower()
        assert "even if prerequisites are not met" in lowered
        assert "still check term" in lowered.lower()

    # B. Don't say term is irrelevant.

    def test_answer_prompt_forbids_term_irrelevant(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "Not eligible.",
            ]),
        )
        prompt = self._get_answer_prompt(agent)
        lowered = prompt.lower()
        assert "never say it is irrelevant" in lowered

    # C. Don't invent prerequisite course codes.

    def test_answer_prompt_forbids_inventing_prereq_codes(self):
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "recommend_courses_for_requirement", '
                '"arguments": {"requirement_tag": "pool", '
                '"completed_courses": []}}',
                "Recommendations.",
            ]),
        )
        prompt = self._get_answer_prompt(agent)
        lowered = prompt.lower()
        assert "never name specific prerequisite course codes" in lowered
        assert "those codes appear" in lowered

    def test_reasoning_prompt_forbids_inventing_prereq_codes(self):
        agent = CoursePlanningAgent()
        prompt = self._get_system_prompt(agent, "What AI courses?")
        lowered = prompt.lower()
        assert "never invent specific prerequisite" in lowered
        assert "those course codes appear" in lowered


class TestDiagnosticFields:
    """Verify last_model_response and parse_error in handle_request result."""

    def test_last_model_response_contains_malformed_on_parse_error(self):
        """parse_error → last_model_response holds the rejected raw text."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "This is not valid JSON at all.",
                "Fallback answer.",
            ]),
        )
        result = agent.handle_request(
            "Can I take CSC384H1?", max_tool_steps=2
        )
        assert result["stop_reason"] == "parse_error"
        assert result["last_model_response"] == "This is not valid JSON at all."
        assert result["parse_error"] is not None
        assert "no json" in result["parse_error"].lower()

    def test_parse_error_is_none_on_finish(self):
        """Explicit finish → parse_error is None."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                '{"action": "finish"}',
                "Final answer.",
            ]),
        )
        result = agent.handle_request("Query.", max_tool_steps=2)
        assert result["stop_reason"] == "finish"
        assert result["last_model_response"] == '{"action": "finish"}'
        assert result["parse_error"] is None

    def test_parse_error_is_none_on_max_steps(self):
        """max_steps completion → parse_error is None."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "This should not be read — max_steps stops first.",
            ]),
        )
        result = agent.handle_request(
            "Can I take CSC384H1?", max_tool_steps=1
        )
        assert result["stop_reason"] == "max_steps"
        assert result["parse_error"] is None

    def test_last_model_response_is_updated_on_success(self):
        """Successful step → last_model_response is the raw tool JSON."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "check_prerequisites", '
                '"arguments": {"course_code": "CSC384H1", '
                '"completed_courses": ["CSC148H1"]}}',
                "Final answer.",
            ]),
        )
        result = agent.handle_request(
            "Can I take CSC384H1?", max_tool_steps=1
        )
        assert result["stop_reason"] == "max_steps"
        assert "check_prerequisites" in result["last_model_response"]

    def test_existing_flat_keys_unchanged(self):
        """Backward-compatible fields still work with new diagnostic fields."""
        agent = CoursePlanningAgent(
            model=_SequenceModel([
                '{"tool_name": "get_course_details", '
                '"arguments": {"course_code": "CSC108H1"}}',
                "Answer.",
            ]),
        )
        result = agent.handle_request("Query.", max_tool_steps=1)
        # Existing flat keys.
        assert "thought" in result
        assert "tool_called" in result
        assert "observation" in result
        assert "final_answer" in result
        assert "steps" in result
        assert "stop_reason" in result
        # New fields.
        assert "last_model_response" in result
        assert "parse_error" in result
        # Values.
        assert result["tool_called"] == "get_course_details"
        assert isinstance(result["last_model_response"], str)
        assert result["parse_error"] is None
