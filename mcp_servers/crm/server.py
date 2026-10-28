"""CRM MCP Server — customer and deal management.

Read tools: list_customers, search_deals, get_deal
Write tools: update_deal_stage

Deals are visible only to their owner and sales leadership.
"""

import logging
from datetime import datetime

from sqlalchemy import select

from company.models import Customer, Deal
from company.principal import Principal
from company.rls import rls_session
from mcp_servers.base import access_denied, tool_result

logger = logging.getLogger(__name__)


def list_customers(
    principal: Principal,
    query: str = "",
    industry: str = "",
    limit: int = 20,
) -> dict:
    """List customers. Customer directory is visible to all."""
    with rls_session(principal) as session:
        stmt = select(Customer)
        if query:
            stmt = stmt.where((Customer.name.ilike(f"%{query}%")) | (Customer.contact_email.ilike(f"%{query}%")))
        if industry:
            stmt = stmt.where(Customer.industry.ilike(f"%{industry}%"))

        stmt = stmt.order_by(Customer.name).limit(limit)
        results = session.execute(stmt).scalars().all()

        return tool_result(
            [
                {
                    "id": c.id,
                    "name": c.name,
                    "industry": c.industry,
                    "contact_email": c.contact_email,
                }
                for c in results
            ]
        )


def search_deals(
    principal: Principal,
    query: str = "",
    stage: str = "",
    customer_id: int | None = None,
    my_deals_only: bool = False,
    limit: int = 20,
) -> dict:
    """Search deals. Filtered by RLS — only visible to owner + sales leadership."""
    with rls_session(principal) as session:
        stmt = select(Deal).join(Customer)
        if query:
            stmt = stmt.where((Deal.title.ilike(f"%{query}%")) | (Customer.name.ilike(f"%{query}%")))
        if stage:
            stmt = stmt.where(Deal.stage == stage)
        if customer_id:
            stmt = stmt.where(Deal.customer_id == customer_id)
        if my_deals_only:
            stmt = stmt.where(Deal.owner_id == principal.user_id)

        stmt = stmt.order_by(Deal.updated_at.desc()).limit(limit)
        results = session.execute(stmt).scalars().all()

        if not results:
            return tool_result([])

        return tool_result(
            [
                {
                    "deal_id": d.deal_id,
                    "title": d.title,
                    "customer_id": d.customer_id,
                    "owner_id": d.owner_id,
                    "value": d.value,
                    "stage": d.stage,
                    "created_at": d.created_at.isoformat(),
                    "updated_at": d.updated_at.isoformat(),
                    "canary": d.canary,
                }
                for d in results
            ]
        )


def get_deal(principal: Principal, deal_id: str) -> dict:
    """Get full deal details. Filtered by RLS."""
    with rls_session(principal) as session:
        stmt = select(Deal).where(Deal.deal_id == deal_id)
        deal = session.execute(stmt).scalar_one_or_none()

        if not deal:
            return access_denied("deal", "Deal not found or access denied.")

        return tool_result(
            {
                "deal_id": deal.deal_id,
                "title": deal.title,
                "customer_id": deal.customer_id,
                "owner_id": deal.owner_id,
                "value": deal.value,
                "stage": deal.stage,
                "created_at": deal.created_at.isoformat(),
                "updated_at": deal.updated_at.isoformat(),
                "canary": deal.canary,
            }
        )


def update_deal_stage(
    principal: Principal,
    deal_id: str,
    new_stage: str,
) -> dict:
    """Update deal stage. Requires human approval."""
    valid_stages = {"prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"}
    if new_stage not in valid_stages:
        return tool_result(None, error=f"Invalid stage. Must be one of: {valid_stages}")

    with rls_session(principal) as session:
        stmt = select(Deal).where(Deal.deal_id == deal_id)
        deal = session.execute(stmt).scalar_one_or_none()

        if not deal:
            return access_denied("deal")

        old_stage = deal.stage
        deal.stage = new_stage
        deal.updated_at = datetime.utcnow()
        session.flush()

        return tool_result(
            {
                "deal_id": deal.deal_id,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "action": "update_deal_stage",
                "requires_approval": True,
            }
        )


TOOLS = {
    "crm_list_customers": {
        "function": list_customers,
        "description": "List or search customers",
        "parameters": {
            "query": {"type": "string"},
            "industry": {"type": "string"},
            "limit": {"type": "integer"},
        },
    },
    "crm_search_deals": {
        "function": search_deals,
        "description": "Search deals (filtered by permissions — owner + sales leadership only)",
        "parameters": {
            "query": {"type": "string"},
            "stage": {"type": "string"},
            "customer_id": {"type": "integer"},
            "my_deals_only": {"type": "boolean"},
            "limit": {"type": "integer"},
        },
    },
    "crm_get_deal": {
        "function": get_deal,
        "description": "Get full deal details by ID",
        "parameters": {
            "deal_id": {"type": "string", "required": True},
        },
    },
    "crm_update_deal_stage": {
        "function": update_deal_stage,
        "description": "Update a deal's stage (requires approval)",
        "parameters": {
            "deal_id": {"type": "string", "required": True},
            "new_stage": {"type": "string", "required": True},
        },
        "write": True,
    },
}
