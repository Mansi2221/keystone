"""FastAPI gateway — the single entry point for the Keystone agent.

- JWT auth on every request
- Identity resolution from the HR system
- Principal propagation to all tool calls
- Audit logging
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from sqlalchemy import select as sa_select

from api.auth import (
    create_access_token,
    get_current_principal,
    get_demo_users,
    resolve_principal,
)
from company.config import settings
from company.database import SessionLocal
from company.models import AuditLog, Employee
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
    demo_users = get_demo_users()
    user_info = demo_users.get(req.username)
    if not user_info:
        raise HTTPException(status_code=400, detail=f"Unknown demo user: {req.username}")

    emp_id = user_info["employee_id"]
    token = create_access_token(emp_id)

    # Resolve from DB for authoritative role/department
    principal = resolve_principal(emp_id)

    return LoginResponse(
        token=token,
        employee_id=emp_id,
        role=principal.role,
        name=user_info.get("name", f"Employee {emp_id}"),
    )


@app.get("/auth/me")
async def get_me(principal: Principal = Depends(get_current_principal)) -> dict:
    """Get the current user's identity and permissions."""
    session = SessionLocal()
    try:
        emp = session.execute(sa_select(Employee).where(Employee.id == principal.user_id)).scalar_one_or_none()
        name = f"{emp.first_name} {emp.last_name}" if emp else principal.employee_id
        title = emp.title if emp else principal.role
    finally:
        session.close()

    return {
        "user_id": principal.user_id,
        "employee_id": principal.employee_id,
        "role": principal.role,
        "department": principal.department,
        "groups": principal.groups,
        "manager_id": principal.manager_id,
        "report_count": len(principal.report_ids),
        "name": name,
        "title": title,
    }


@app.get("/auth/demo-users")
async def list_demo_users() -> list[dict]:
    """List available demo users for the user switcher."""
    demo_users = get_demo_users()
    users = []
    for key, info in demo_users.items():
        try:
            p = resolve_principal(info["employee_id"])
            users.append({
                "key": key,
                "employee_id": info["employee_id"],
                "role": p.role,
                "department": p.department,
                "name": info.get("name", p.employee_id),
                "title": info.get("description", p.role),
                "description": info.get("description", key),
                "groups": p.groups,
            })
        except Exception:
            users.append({
                "key": key,
                "employee_id": info["employee_id"],
                "role": info.get("role", "unknown"),
                "department": info.get("department", "Unknown"),
                "name": info.get("name", key),
                "title": info.get("description", key),
                "description": info.get("description", key),
                "groups": [],
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
    """Chat with the Keystone agent."""
    from agent.graph import run_agent

    state = run_agent(
        message=req.message,
        principal=principal,
        conversation_id=req.conversation_id or "",
    )

    # Build pending actions list
    pending = []
    if state.needs_approval and state.pending_action:
        pa = state.pending_action
        pending.append({
            "tool": pa.tool_name,
            "arguments": pa.arguments,
            "description": f"Pending: {pa.tool_name}",
        })

    return ChatResponse(
        reply=state.final_response or state.draft_response or "I couldn't generate a response.",
        sources=[
            {"type": s.source_type, "id": s.source_id, "title": s.title}
            for s in state.sources
        ],
        pending_actions=pending,
        trace_id=state.trace_id,
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


# --- Response cache (same user + question → replay cached SSE events) ---
# Key includes user_id AND role, so cached responses never cross users.
# Call clear_response_cache() after seed data or policy changes.

_response_cache: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_key_for(user_id: int, role: str, message: str) -> str:
    raw = f"{user_id}:{role}:{message.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def clear_response_cache() -> int:
    """Clear the in-memory response cache. Returns number of entries cleared."""
    n = len(_response_cache)
    _response_cache.clear()
    return n


# --- SSE Streaming chat endpoint ---

@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Stream agent events as Server-Sent Events."""
    from agent.graph import run_agent

    # Check cache
    ck = _cache_key_for(principal.user_id, principal.role, req.message)
    cached = _response_cache.get(ck)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        logger.info("Cache hit for user %d: %s", principal.user_id, req.message[:40])

        async def replay():
            for line in cached[1]:
                yield line
        return StreamingResponse(replay(), media_type="text/event-stream")

    async def generate():
        events: list[str] = []
        is_error = False
        try:
            # Run agent synchronously in a thread
            state = await asyncio.to_thread(
                run_agent,
                message=req.message,
                principal=principal,
                conversation_id=req.conversation_id or "",
            )

            # Emit node events from the execution path
            for node_name in state.node_path:
                event: dict[str, Any] = {"type": "node", "node": node_name, "data": {}}
                if node_name == "planner":
                    event["data"] = {"plan": state.plan, "tools": state.planned_tools}
                line = f"data: {json.dumps(event)}\n\n"
                events.append(line)
                yield line

            # Emit tool start/result pairs
            for tc in state.tool_calls:
                line = f"data: {json.dumps({'type': 'tool_start', 'tool': tc.tool_name, 'arguments': tc.arguments})}\n\n"
                events.append(line)
                yield line
                if tc.result is not None:
                    line = f"data: {json.dumps({'type': 'tool_result', 'tool': tc.tool_name, 'success': tc.result.get('success', False), 'data': tc.result.get('data')})}\n\n"
                    events.append(line)
                    yield line

            # Emit approval if needed
            if state.needs_approval and state.pending_action:
                pa = state.pending_action
                line = f"data: {json.dumps({'type': 'approval_needed', 'tool': pa.tool_name, 'arguments': pa.arguments})}\n\n"
                events.append(line)
                yield line

            # Emit sources
            if state.sources:
                sources = [{"type": s.source_type, "id": s.source_id, "title": s.title} for s in state.sources]
                line = f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
                events.append(line)
                yield line

            # Emit response or blocked
            if state.blocked:
                line = f"data: {json.dumps({'type': 'blocked', 'reason': state.block_reason})}\n\n"
                events.append(line)
                yield line
            else:
                response_text = state.final_response or state.draft_response or ""
                line = f"data: {json.dumps({'type': 'response', 'text': response_text})}\n\n"
                events.append(line)
                yield line

            line = f"data: {json.dumps({'type': 'done', 'trace_id': state.trace_id})}\n\n"
            events.append(line)
            yield line

        except Exception as e:
            is_error = True
            logger.exception("SSE stream error")
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str or "quota" in err_str:
                msg = "The AI model is busy right now. Please wait a moment and try again."
            elif "timeout" in err_str:
                msg = "The request took too long. Please try a simpler question."
            else:
                msg = "Something went wrong processing your request. Please try again."
            yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"

        # Cache successful responses (not errors)
        if not is_error and events:
            _response_cache[ck] = (time.time(), events)

    return StreamingResponse(generate(), media_type="text/event-stream")


# --- Approvals endpoints ---

@app.get("/approvals")
async def list_approvals(
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    """List pending approvals. Currently ephemeral (managed during agent runs)."""
    return []


class ApprovalDecision(BaseModel):
    approved: bool


@app.post("/approvals/{approval_id}")
async def decide_approval(
    approval_id: str,
    decision: ApprovalDecision,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Approve or deny a pending action. Placeholder for persistent approval queue."""
    raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")


# --- Trace endpoint ---

@app.get("/trace/{trace_id}")
async def get_trace(
    trace_id: str,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Get trace data for a specific agent run."""
    session = SessionLocal()
    try:
        from sqlalchemy import select

        stmt = select(AuditLog).where(AuditLog.trace_id == trace_id).order_by(AuditLog.timestamp)
        if not principal.is_executive():
            stmt = stmt.where(AuditLog.user_id == principal.user_id)

        results = session.execute(stmt).scalars().all()
        events = [
            {
                "id": a.id,
                "timestamp": a.timestamp.isoformat(),
                "tool": a.tool,
                "arguments": a.arguments,
                "policy_decision": a.policy_decision,
                "result_status": a.result_status,
            }
            for a in results
        ]
        return {"trace_id": trace_id, "events": events}
    finally:
        session.close()


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
