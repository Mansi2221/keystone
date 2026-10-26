"""Tests for agent state and graph structure."""

import pytest

from agent.state import AgentState, ToolCall, Source
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
            user_id=1, employee_id="MF-0001",
            role="executive", department="Operations",
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
            user_id=1, employee_id="MF-0001",
            role="executive", department="Operations",
        )
        state = AgentState(
            principal=principal,
            draft_response="The employee directory shows 120 employees across 5 departments.",
        )
        result = output_scanner_node(state)
        assert not result.blocked
        assert result.final_response == state.draft_response
