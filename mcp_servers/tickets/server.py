"""Ticketing MCP Server — read and write tools for tickets.

Read tools: search_tickets, get_ticket, list_ticket_comments
Write tools: update_ticket_status, add_ticket_comment
"""

import logging
from datetime import datetime

from sqlalchemy import select

from company.models import Employee, Ticket, TicketComment
from company.principal import Principal
from company.rls import rls_session
from mcp_servers.base import access_denied, tool_result

logger = logging.getLogger(__name__)


def search_tickets(
    principal: Principal,
    query: str = "",
    status: str = "",
    category: str = "",
    priority: str = "",
    assigned_to_me: bool = False,
    limit: int = 20,
) -> dict:
    """Search tickets. Results filtered by RLS based on user's permissions."""
    with rls_session(principal) as session:
        stmt = select(Ticket)
        if query:
            stmt = stmt.where(
                (Ticket.title.ilike(f"%{query}%"))
                | (Ticket.description.ilike(f"%{query}%"))
                | (Ticket.ticket_id.ilike(f"%{query}%"))
            )
        if status:
            stmt = stmt.where(Ticket.status == status)
        if category:
            stmt = stmt.where(Ticket.category == category)
        if priority:
            stmt = stmt.where(Ticket.priority == priority)
        if assigned_to_me:
            stmt = stmt.where(Ticket.assignee_id == principal.user_id)

        stmt = stmt.order_by(Ticket.updated_at.desc()).limit(limit)
        results = session.execute(stmt).scalars().all()

        return tool_result([
            {
                "ticket_id": t.ticket_id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "category": t.category,
                "team": t.team,
                "owner_id": t.owner_id,
                "assignee_id": t.assignee_id,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
                "canary": t.canary,
            }
            for t in results
        ])


def get_ticket(principal: Principal, ticket_id: str) -> dict:
    """Get full details of a specific ticket."""
    with rls_session(principal) as session:
        stmt = select(Ticket).where(Ticket.ticket_id == ticket_id)
        ticket = session.execute(stmt).scalar_one_or_none()

        if not ticket:
            return access_denied("ticket", "Ticket not found or access denied.")

        return tool_result({
            "ticket_id": ticket.ticket_id,
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "category": ticket.category,
            "team": ticket.team,
            "owner_id": ticket.owner_id,
            "assignee_id": ticket.assignee_id,
            "created_at": ticket.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
            "canary": ticket.canary,
        })


def list_ticket_comments(principal: Principal, ticket_id: str, limit: int = 50) -> dict:
    """List comments on a ticket."""
    with rls_session(principal) as session:
        # First check ticket is visible
        ticket_stmt = select(Ticket).where(Ticket.ticket_id == ticket_id)
        ticket = session.execute(ticket_stmt).scalar_one_or_none()
        if not ticket:
            return access_denied("ticket comments")

        stmt = (
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket.id)
            .order_by(TicketComment.created_at)
            .limit(limit)
        )
        results = session.execute(stmt).scalars().all()
        return tool_result([
            {
                "id": c.id,
                "author_id": c.author_id,
                "content": c.content,
                "created_at": c.created_at.isoformat(),
            }
            for c in results
        ])


def update_ticket_status(
    principal: Principal,
    ticket_id: str,
    new_status: str,
) -> dict:
    """Update the status of a ticket. Requires human approval."""
    valid_statuses = {"open", "in_progress", "resolved", "closed"}
    if new_status not in valid_statuses:
        return tool_result(None, error=f"Invalid status. Must be one of: {valid_statuses}")

    with rls_session(principal) as session:
        stmt = select(Ticket).where(Ticket.ticket_id == ticket_id)
        ticket = session.execute(stmt).scalar_one_or_none()
        if not ticket:
            return access_denied("ticket")

        old_status = ticket.status
        ticket.status = new_status
        ticket.updated_at = datetime.utcnow()
        session.flush()

        return tool_result({
            "ticket_id": ticket.ticket_id,
            "old_status": old_status,
            "new_status": new_status,
            "action": "update_ticket_status",
            "requires_approval": True,
        })


def add_ticket_comment(
    principal: Principal,
    ticket_id: str,
    content: str,
) -> dict:
    """Add a comment to a ticket. Requires human approval."""
    with rls_session(principal) as session:
        stmt = select(Ticket).where(Ticket.ticket_id == ticket_id)
        ticket = session.execute(stmt).scalar_one_or_none()
        if not ticket:
            return access_denied("ticket")

        comment = TicketComment(
            ticket_id=ticket.id,
            author_id=principal.user_id,
            content=content,
            created_at=datetime.utcnow(),
        )
        session.add(comment)
        session.flush()

        return tool_result({
            "ticket_id": ticket_id,
            "comment_id": comment.id,
            "action": "add_ticket_comment",
            "requires_approval": True,
        })


TOOLS = {
    "tickets_search": {
        "function": search_tickets,
        "description": "Search tickets by keyword, status, category, or priority",
        "parameters": {
            "query": {"type": "string", "description": "Search term"},
            "status": {"type": "string", "description": "Filter by status"},
            "category": {"type": "string", "description": "Filter by category"},
            "priority": {"type": "string", "description": "Filter by priority"},
            "assigned_to_me": {"type": "boolean", "description": "Show only my assigned tickets"},
            "limit": {"type": "integer", "description": "Max results"},
        },
    },
    "tickets_get": {
        "function": get_ticket,
        "description": "Get full details of a specific ticket by ID",
        "parameters": {
            "ticket_id": {"type": "string", "required": True},
        },
    },
    "tickets_list_comments": {
        "function": list_ticket_comments,
        "description": "List comments on a ticket",
        "parameters": {
            "ticket_id": {"type": "string", "required": True},
            "limit": {"type": "integer"},
        },
    },
    "tickets_update_status": {
        "function": update_ticket_status,
        "description": "Update ticket status (requires approval)",
        "parameters": {
            "ticket_id": {"type": "string", "required": True},
            "new_status": {"type": "string", "required": True},
        },
        "write": True,
    },
    "tickets_add_comment": {
        "function": add_ticket_comment,
        "description": "Add a comment to a ticket (requires approval)",
        "parameters": {
            "ticket_id": {"type": "string", "required": True},
            "content": {"type": "string", "required": True},
        },
        "write": True,
    },
}
