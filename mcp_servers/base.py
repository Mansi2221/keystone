"""Base MCP server utilities shared across all system servers.

Every MCP tool call requires a Principal passed from the gateway.
The MCP servers never accept a principal chosen by the model.
"""

import json
import logging
from typing import Any

from company.principal import Principal

logger = logging.getLogger(__name__)


def parse_principal(principal_json: str) -> Principal:
    """Parse a principal from the JSON string passed by the gateway.

    The gateway serializes the principal from the JWT + HR lookup.
    MCP servers must never construct their own principal.
    """
    data = json.loads(principal_json)
    return Principal(
        user_id=data["user_id"],
        employee_id=data["employee_id"],
        role=data["role"],
        department=data["department"],
        groups=data.get("groups", []),
        manager_id=data.get("manager_id"),
        report_ids=data.get("report_ids", []),
    )


def tool_result(data: Any, *, error: str | None = None) -> dict:
    """Standard tool result format."""
    if error:
        return {"success": False, "error": error, "data": None}
    return {"success": True, "error": None, "data": data}


def access_denied(resource: str, reason: str = "") -> dict:
    """Standard access denied response.

    Does not reveal the content of the restricted resource.
    """
    msg = f"Access denied: you do not have permission to access {resource}."
    if reason:
        msg += f" {reason}"
    return tool_result(None, error=msg)
