"""FastAPI gateway — the single entry point for the Keystone agent.

- JWT auth on every request
- Identity resolution from the HR system
- Principal propagation to all tool calls
- Audit logging
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.auth import (
    DEMO_USERS,
    create_access_token,
    get_current_principal,
    resolve_principal,
)
from company.config import settings
from company.database import SessionLocal
from company.models import AuditLog
from company.principal import Principal
from mcp_servers.registry import get_tool_definitions, invoke_tool, is_write_tool

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Keystone API",
    description="Permission-aware enterprise AI agent gateway",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth endpoints ---

class LoginRequest(BaseModel):
    username: str  # demo user key from DEMO_USERS


class LoginResponse(BaseModel):
    token: str
    employee_id: int
    role: str
    name: str


class TokenResponse(BaseModel):
    token: str


@app.post("/auth/login", response_model=LoginResponse)
async def dev_login(req: LoginRequest) -> LoginResponse:
    """Dev login endpoint — returns a JWT for any seeded demo user."""
    user_info = DEMO_USERS.get(req.username)
    if not user_info:
        raise HTTPException(status_code=400, detail=f"Unknown demo user: {req.username}")

    emp_id = user_info["employee_id"]
    token = create_access_token(emp_id)

    # Resolve name from DB
    principal = resolve_principal(emp_id)

    return LoginResponse(
        token=token,
        employee_id=emp_id,
        role=principal.role,
        name=f"Employee {emp_id} ({principal.role})",
    )


@app.get("/auth/me")
async def get_me(principal: Principal = Depends(get_current_principal)) -> dict:
    """Get the current user's identity and permissions."""
    return {
        "user_id": principal.user_id,
        "employee_id": principal.employee_id,
        "role": principal.role,
        "department": principal.department,
        "groups": principal.groups,
        "manager_id": principal.manager_id,
        "report_count": len(principal.report_ids),
    }


@app.get("/auth/demo-users")
async def list_demo_users() -> list[dict]:
    """List available demo users for the user switcher."""
    users = []
    for key, info in DEMO_USERS.items():
        try:
            p = resolve_principal(info["employee_id"])
            users.append({
                "key": key,
                "employee_id": info["employee_id"],
                "role": p.role,
                "department": p.department,
                "name": f"{p.employee_id} — {p.role} ({p.department})",
                "description": info["description"],
            })
        except Exception:
            users.append({
                "key": key,
                "employee_id": info["employee_id"],
                "role": info["role"],
                "description": info["description"],
            })
    return users


# --- Tool endpoints ---

@app.get("/tools")
async def list_tools() -> list[dict]:
    """List all available tools with their definitions."""
    return get_tool_definitions()


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    requires_approval: bool = False
    audit_id: int | None = None


@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(
    req: ToolCallRequest,
    principal: Principal = Depends(get_current_principal),
) -> ToolCallResponse:
    """Invoke a tool with the current user's principal.

    The principal is always resolved from the JWT — never from the request body.
    Write tools are flagged as requiring approval.
    """
    requires_approval = is_write_tool(req.tool_name)

    # Log the attempt
    audit_entry = _create_audit_log(
        principal=principal,
        tool=req.tool_name,
        arguments=req.arguments,
        policy_decision="allow",  # Cerbos check happens inside tool
        result_status="pending",
    )

    # Invoke tool
    result = invoke_tool(req.tool_name, principal, **req.arguments)

    # Update audit
    _update_audit_status(
        audit_entry,
        result_status="success" if result.get("success") else "denied",
    )

    return ToolCallResponse(
        success=result.get("success", False),
        data=result.get("data"),
        error=result.get("error"),
        requires_approval=requires_approval,
        audit_id=audit_entry,
    )


# --- Agent chat endpoint (placeholder for Phase 4) ---

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[dict] = []
    pending_actions: list[dict] = []
    trace_id: str | None = None


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    principal: Principal = Depends(get_current_principal),
) -> ChatResponse:
    """Chat with the Keystone agent. (Full implementation in Phase 4.)"""
    return ChatResponse(
        reply="Agent chat will be implemented in Phase 4. "
        f"You are logged in as {principal.employee_id} ({principal.role}).",
        sources=[],
        pending_actions=[],
    )


# --- Audit log endpoints ---

@app.get("/audit")
async def get_audit_log(
    limit: int = 50,
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    """Get recent audit log entries. Visible to executives and the user's own entries."""
    session = SessionLocal()
    try:
        from sqlalchemy import select
        from company.models import AuditLog

        stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())
        if not principal.is_executive():
            stmt = stmt.where(AuditLog.user_id == principal.user_id)
        stmt = stmt.limit(limit)

        results = session.execute(stmt).scalars().all()
        return [
            {
                "id": a.id,
                "timestamp": a.timestamp.isoformat(),
                "user_id": a.user_id,
                "role": a.role,
                "tool": a.tool,
                "arguments": a.arguments,
                "policy_decision": a.policy_decision,
                "result_status": a.result_status,
                "trace_id": a.trace_id,
            }
            for a in results
        ]
    finally:
        session.close()


# --- Health ---

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "keystone"}


# --- Helpers ---

def _create_audit_log(
    principal: Principal,
    tool: str,
    arguments: dict,
    policy_decision: str,
    result_status: str,
    trace_id: str | None = None,
) -> int:
    """Create an audit log entry and return its ID."""
    session = SessionLocal()
    try:
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            user_id=principal.user_id,
            role=principal.role,
            tool=tool,
            arguments=arguments,
            policy_decision=policy_decision,
            result_status=result_status,
            trace_id=trace_id,
        )
        session.add(entry)
        session.commit()
        return entry.id
    except Exception:
        session.rollback()
        logger.exception("Failed to create audit log")
        return 0
    finally:
        session.close()


def _update_audit_status(audit_id: int, result_status: str) -> None:
    """Update an audit log entry's result status."""
    if not audit_id:
        return
    session = SessionLocal()
    try:
        entry = session.get(AuditLog, audit_id)
        if entry:
            entry.result_status = result_status
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
