"""Tool registry — aggregates all MCP server tools into a single registry.

The agent and API gateway use this to discover and invoke tools.
"""

import logging
from typing import Any, Callable

from company.principal import Principal
from mcp_servers.chat.server import TOOLS as CHAT_TOOLS
from mcp_servers.crm.server import TOOLS as CRM_TOOLS
from mcp_servers.docs.server import TOOLS as DOCS_TOOLS
from mcp_servers.hr.server import TOOLS as HR_TOOLS
from mcp_servers.tickets.server import TOOLS as TICKETS_TOOLS

logger = logging.getLogger(__name__)

# Merged tool registry
ALL_TOOLS: dict[str, dict[str, Any]] = {
    **HR_TOOLS,
    **TICKETS_TOOLS,
    **DOCS_TOOLS,
    **CHAT_TOOLS,
    **CRM_TOOLS,
}


def get_tool_definitions() -> list[dict]:
    """Get tool definitions in a format suitable for the LLM."""
    definitions = []
    for name, info in ALL_TOOLS.items():
        params = {}
        required = []
        for pname, pinfo in info.get("parameters", {}).items():
            params[pname] = {
                "type": pinfo.get("type", "string"),
                "description": pinfo.get("description", ""),
            }
            if pinfo.get("required"):
                required.append(pname)

        definitions.append({
            "name": name,
            "description": info["description"],
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required,
            },
            "is_write": info.get("write", False),
        })
    return definitions


def invoke_tool(name: str, principal: Principal, **kwargs: Any) -> dict:
    """Invoke a tool by name with the given principal and arguments.

    The principal is always passed from the gateway, never from the model.
    """
    if name not in ALL_TOOLS:
        return {"success": False, "error": f"Unknown tool: {name}", "data": None}

    tool_info = ALL_TOOLS[name]
    func: Callable = tool_info["function"]

    try:
        result = func(principal, **kwargs)
        logger.info("Tool %s invoked by user %d (%s)", name, principal.user_id, principal.role)
        return result
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return {"success": False, "error": str(e), "data": None}


def is_write_tool(name: str) -> bool:
    """Check if a tool is a write tool (requires human approval)."""
    if name not in ALL_TOOLS:
        return False
    return ALL_TOOLS[name].get("write", False)
