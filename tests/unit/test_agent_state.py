"""Tests for agent state and graph structure."""

import pytest

from agent.state import AgentState, Source, ToolCall
from company.principal import Principal


@pytest.mark.unit
class TestAgentState:
    def test_default_state(self):
        state = AgentState()
        assert state.user_message == ""
        assert state.principal is None
        assert state.blocked is False
        assert state.iteration_count == 0

    def test_state_with_principal(self):
        principal = Principal(
            user_id=1,
            employee_id="MF-0001",
            role="executive",
            department="Operations",
        )
        state = AgentState(user_message="Hello", principal=principal)
        assert state.principal.is_executive()

    def test_tool_call(self):
        tc = ToolCall(tool_name="hr_search_employees", arguments={"query": "test"})
        assert tc.result is None
        assert tc.policy_decision == "pending"
        assert tc.approved is None

    def test_source(self):
        s = Source(source_type="document", source_id="DOC-0001", title="Test Doc")
        assert s.source_type == "document"
        assert s.source_id == "DOC-0001"


@pytest.mark.unit
class TestGraphStructure:
    def test_graph_builds(self):
        """The graph should compile without errors."""
        from agent.graph import build_graph

        graph = build_graph()
        assert graph is not None

    def test_planner_node_no_principal(self):
        """Planner should handle missing principal gracefully."""
        from agent.graph import planner_node

        state = AgentState(user_message="test")
        result = planner_node(state)
        assert result.blocked is True
        assert "principal" in result.error.lower()

    def test_tool_executor_no_principal(self):
        """Executor should handle missing principal."""
        from agent.graph import tool_executor_node

        state = AgentState()
        result = tool_executor_node(state)
        assert result.error == "No principal"

    def test_output_scanner_no_flags_on_clean_response(self):
        """Output scanner should pass clean responses."""
        from agent.graph import output_scanner_node

        principal = Principal(
            user_id=1,
            employee_id="MF-0001",
            role="executive",
            department="Operations",
        )
        state = AgentState(
            principal=principal,
            draft_response="The employee directory shows 120 employees across 5 departments.",
        )
        result = output_scanner_node(state)
        assert not result.blocked
        assert result.final_response == state.draft_response

    def test_tool_router_no_planned_tools(self):
        """Router should return immediately with no planned tools."""
        from agent.graph import tool_router_node

        state = AgentState(user_message="hello")
        result = tool_router_node(state)
        assert result.tool_calls == []

    def test_tool_router_fallback_on_llm_failure(self):
        """Router should create empty-arg calls if LLM is unavailable."""
        import os

        from agent.graph import tool_router_node

        # Force an invalid provider so the LLM call fails
        old_key = os.environ.get("OPENAI_API_KEY", "")
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["LLM_PROVIDER"] = "openai"
        os.environ["LLM_MODEL"] = "invalid-model"
        try:
            principal = Principal(
                user_id=20,
                employee_id="MF-0020",
                role="individual_contributor",
                department="Engineering",
            )
            state = AgentState(
                user_message="search employees named Jordan",
                principal=principal,
                planned_tools=["hr_search_employees"],
            )
            result = tool_router_node(state)
            # Should still create tool calls (with empty args as fallback)
            assert len(result.tool_calls) == 1
            assert result.tool_calls[0].tool_name == "hr_search_employees"
        finally:
            os.environ["OPENAI_API_KEY"] = old_key

    def test_coerce_arg_types(self):
        """Argument coercion should convert string IDs to ints."""
        from agent.graph import _coerce_arg_types

        props = {
            "employee_id": {"type": "integer", "description": "Employee ID"},
            "query": {"type": "string", "description": "Search term"},
        }
        result = _coerce_arg_types({"employee_id": "20", "query": "test"}, props)
        assert result["employee_id"] == 20
        assert result["query"] == "test"

    def test_coerce_arg_types_already_correct(self):
        """Coercion should be a no-op when types already match."""
        from agent.graph import _coerce_arg_types

        props = {"employee_id": {"type": "integer"}}
        result = _coerce_arg_types({"employee_id": 42}, props)
        assert result["employee_id"] == 42

    def test_coerce_arg_types_unknown_key(self):
        """Unknown keys should pass through unchanged."""
        from agent.graph import _coerce_arg_types

        result = _coerce_arg_types({"extra": "value"}, {})
        assert result["extra"] == "value"


@pytest.mark.unit
class TestEvalRunner:
    def test_build_principal(self):
        """_build_principal should return a principal with the correct user_id."""
        from evals.runner import _build_principal

        p = _build_principal({"role": "contractor", "employee_id": 25})
        assert p.user_id == 25
        # Role comes from DB if available, otherwise from the spec
        assert p.role in ("contractor", "individual_contributor")

    def test_run_case_without_agent(self):
        """_run_case should handle agent invocation failure gracefully."""
        from evals.runner import _run_case

        case = {
            "id": "test-001",
            "user": {"role": "contractor", "employee_id": 25},
            "message": "Show me salaries",
            "tags": ["test"],
        }
        # canary_match scoring — without a running DB, agent will fail
        # but the case should still return a result dict
        result = _run_case(case, "canary_match")
        assert result["case_id"] == "test-001"
        assert "agent_response" in result
        assert "pass" in result

    def test_run_case_deterministic_without_agent(self):
        """Deterministic scoring should work even on agent failure."""
        from evals.runner import _run_case

        case = {
            "id": "test-002",
            "user": {"role": "individual_contributor", "employee_id": 20},
            "message": "Search employees named Jordan",
            "expected_tools": ["hr_search_employees"],
            "tags": ["test"],
        }
        result = _run_case(case, "deterministic")
        assert result["case_id"] == "test-002"
        assert "pass" in result

    def test_run_case_llm_judge_without_agent(self):
        """LLM judge scoring should work even on agent failure."""
        from evals.runner import _run_case

        case = {
            "id": "test-003",
            "user": {"role": "executive", "employee_id": 1},
            "message": "How many employees?",
            "expected_answer": "120 employees",
            "tags": ["test"],
        }
        result = _run_case(case, "llm_judge")
        assert result["case_id"] == "test-003"
        assert "pass" in result
        assert "score" in result
