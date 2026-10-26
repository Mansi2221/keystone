"""Chat MCP Server — read and write tools for team chat.

Read tools: list_channels, search_messages, get_channel_messages
Write tools: post_message

Private channels and DMs are only visible to their members (enforced by RLS).
"""

import logging
from datetime import datetime

from sqlalchemy import select

from company.models import ChatChannel, ChatMessage, ChannelMember
from company.principal import Principal
from company.rls import rls_session
from mcp_servers.base import access_denied, tool_result

logger = logging.getLogger(__name__)


def list_channels(
    principal: Principal,
    include_dms: bool = False,
) -> dict:
    """List channels visible to the current user. Filtered by RLS."""
    with rls_session(principal) as session:
        stmt = select(ChatChannel)
        if not include_dms:
            stmt = stmt.where(ChatChannel.is_dm == False)
        stmt = stmt.order_by(ChatChannel.name)

        results = session.execute(stmt).scalars().all()
        return tool_result([
            {
                "id": c.id,
                "name": c.name,
                "is_private": c.is_private,
                "is_dm": c.is_dm,
                "department": c.department,
            }
            for c in results
        ])


def get_channel_messages(
    principal: Principal,
    channel_id: int,
    limit: int = 50,
    before: str | None = None,
) -> dict:
    """Get messages from a channel. Filtered by RLS (channel must be visible)."""
    with rls_session(principal) as session:
        # Check channel is visible via RLS
        ch = session.execute(
            select(ChatChannel).where(ChatChannel.id == channel_id)
        ).scalar_one_or_none()

        if not ch:
            return access_denied("channel", "Channel not found or access denied.")

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.channel_id == channel_id)
        )
        if before:
            stmt = stmt.where(ChatMessage.timestamp < datetime.fromisoformat(before))

        stmt = stmt.order_by(ChatMessage.timestamp.desc()).limit(limit)
        results = session.execute(stmt).scalars().all()

        return tool_result({
            "channel": {"id": ch.id, "name": ch.name},
            "messages": [
                {
                    "id": m.id,
                    "author_id": m.author_id,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in reversed(results)  # chronological order
            ],
        })


def search_messages(
    principal: Principal,
    query: str,
    channel_id: int | None = None,
    limit: int = 20,
) -> dict:
    """Search messages across visible channels."""
    with rls_session(principal) as session:
        stmt = (
            select(ChatMessage)
            .join(ChatChannel)
            .where(ChatMessage.content.ilike(f"%{query}%"))
        )
        if channel_id:
            stmt = stmt.where(ChatMessage.channel_id == channel_id)

        stmt = stmt.order_by(ChatMessage.timestamp.desc()).limit(limit)
        results = session.execute(stmt).scalars().all()

        return tool_result([
            {
                "id": m.id,
                "channel_id": m.channel_id,
                "author_id": m.author_id,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in results
        ])


def post_message(
    principal: Principal,
    channel_id: int,
    content: str,
) -> dict:
    """Post a message to a channel. Requires human approval."""
    with rls_session(principal) as session:
        ch = session.execute(
            select(ChatChannel).where(ChatChannel.id == channel_id)
        ).scalar_one_or_none()

        if not ch:
            return access_denied("channel")

        # Verify membership for private channels
        if ch.is_private:
            member = session.execute(
                select(ChannelMember).where(
                    ChannelMember.channel_id == channel_id,
                    ChannelMember.employee_id == principal.user_id,
                )
            ).scalar_one_or_none()
            if not member:
                return access_denied("channel", "You are not a member of this private channel.")

        msg = ChatMessage(
            channel_id=channel_id,
            author_id=principal.user_id,
            content=content,
            timestamp=datetime.utcnow(),
        )
        session.add(msg)
        session.flush()

        return tool_result({
            "message_id": msg.id,
            "channel_id": channel_id,
            "channel_name": ch.name,
            "action": "post_message",
            "requires_approval": True,
        })


TOOLS = {
    "chat_list_channels": {
        "function": list_channels,
        "description": "List visible chat channels",
        "parameters": {
            "include_dms": {"type": "boolean", "description": "Include DM channels"},
        },
    },
    "chat_get_messages": {
        "function": get_channel_messages,
        "description": "Get messages from a specific channel",
        "parameters": {
            "channel_id": {"type": "integer", "required": True},
            "limit": {"type": "integer"},
            "before": {"type": "string", "description": "ISO datetime to paginate before"},
        },
    },
    "chat_search": {
        "function": search_messages,
        "description": "Search messages across visible channels",
        "parameters": {
            "query": {"type": "string", "required": True},
            "channel_id": {"type": "integer", "description": "Limit to specific channel"},
            "limit": {"type": "integer"},
        },
    },
    "chat_post_message": {
        "function": post_message,
        "description": "Post a message to a channel (requires approval)",
        "parameters": {
            "channel_id": {"type": "integer", "required": True},
            "content": {"type": "string", "required": True},
        },
        "write": True,
    },
}
