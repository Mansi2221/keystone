"""Agent state definition for the LangGraph graph."""

from dataclasses import dataclass, field
from typing import Any

from company.principal import Principal


@dataclass
class ToolCall:
    """A pending or completed tool call."""

    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    policy_decision: str = "pending"  # pending, allow, deny
    approved: bool | None = None  # None = not a write tool, True/False for writes


@dataclass
class Source:
    """A cited source from tool results."""

    source_type: str  # document, ticket, message, employee, deal
    source_id: str
    title: str = ""
    snippet: str = ""


@dataclass
class AgentState:
    """Full state for the Keystone agent graph."""

    # Input
    user_message: str = ""
    principal: Principal | None = None
    conversation_id: str = ""

    # Planning
    plan: str = ""
    planned_tools: list[str] = field(default_factory=list)

    # Tool execution
    tool_calls: list[ToolCall] = field(default_factory=list)
    current_tool_index: int = 0

    # Results and response
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    draft_response: str = ""
    final_response: str = ""

    # Guards
    input_guard_flags: list[str] = field(default_factory=list)
    output_guard_flags: list[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: str = ""

    # Control flow
    needs_approval: bool = False
    pending_action: ToolCall | None = None
    approval_granted: bool | None = None

    # Tracing
    trace_id: str = ""
    node_path: list[str] = field(default_factory=list)

    # Error handling
    error: str = ""
    iteration_count: int = 0
    max_iterations: int = 10
