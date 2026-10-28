"""Deterministic security tests — no LLM needed.

Tests that each demo user's tool calls return ONLY permitted rows via RLS + guards.
Runs against a seeded Postgres with RLS enabled.
"""

import os
import re
import pytest

from company.principal import Principal
from agent.guards import check_tool_permission, scan_output_for_leaks, CANARY_PATTERN

# Skip entire module if no database URL
pytestmark = [
    pytest.mark.security,
    pytest.mark.skipif(
        not os.getenv("DATABASE_URL"),
        reason="DATABASE_URL not set — need a seeded Postgres",
    ),
]


# ── Principals for each demo role ──────────────────────────────────

CEO = Principal(
    user_id=1, employee_id="MF-0001", role="executive",
    department="Executive", groups=["leadership", "board_access"],
)

IC_ENGINEER = Principal(
    user_id=22, employee_id="MF-0022", role="individual_contributor",
    department="Engineering", groups=["engineering", "engineering_all"],
)

CONTRACTOR = Principal(
    user_id=61, employee_id="MF-0061", role="contractor",
    department="Engineering", groups=["engineering", "engineering_all"],
)

HR_PARTNER = Principal(
    user_id=5, employee_id="MF-0005", role="hr_partner",
    department="HR", groups=["hr", "hr_all"],
)

SALES_REP = Principal(
    user_id=9, employee_id="MF-0009", role="sales_rep",
    department="Sales", groups=["sales", "sales_all"],
)

MANAGER = Principal(
    user_id=3, employee_id="MF-0003", role="manager",
    department="Sales", groups=["sales", "sales_all", "leadership"],
    report_ids=[9, 10, 11, 12],
)

FINANCE = Principal(
    user_id=7, employee_id="MF-0007", role="finance_analyst",
    department="Finance", groups=["finance", "finance_all"],
)


class TestSalaryRLS:
    """Salary data must only be visible to authorized users."""

    def test_contractor_cannot_see_any_salary(self):
        from mcp_servers.hr.server import get_salary
        result = get_salary(CONTRACTOR, employee_id=CONTRACTOR.user_id)
        assert result.get("error") or not result.get("data"), \
            "Contractor should not see any salary data (including own)"

    def test_ic_sees_own_salary_only(self):
        from mcp_servers.hr.server import get_salary
        # Own salary: allowed
        own = get_salary(IC_ENGINEER, employee_id=IC_ENGINEER.user_id)
        assert own.get("success"), "IC should see own salary"

        # Another person's salary: denied
        other = get_salary(IC_ENGINEER, employee_id=1)
        assert other.get("error") or not other.get("data"), \
            "IC should not see CEO's salary"

    def test_manager_sees_report_salary(self):
        from mcp_servers.hr.server import get_salary
        # Report's salary: allowed
        report = get_salary(MANAGER, employee_id=9)
        assert report.get("success"), "Manager should see report's salary"

    def test_manager_cannot_see_non_report_salary(self):
        from mcp_servers.hr.server import get_salary
        # Non-report: denied by guard
        denial = check_tool_permission("hr_get_salary", {"employee_id": 22}, MANAGER)
        assert denial is not None, "Manager should be denied salary for non-report"

    def test_hr_sees_all_salaries(self):
        from mcp_servers.hr.server import get_salary
        result = get_salary(HR_PARTNER, employee_id=22)
        assert result.get("success"), "HR should see any employee's salary"

    def test_executive_sees_all_salaries(self):
        from mcp_servers.hr.server import get_salary
        result = get_salary(CEO, employee_id=22)
        assert result.get("success"), "CEO should see any employee's salary"

    def test_finance_cannot_see_salary(self):
        denial = check_tool_permission("hr_get_salary", {"employee_id": 22}, FINANCE)
        assert denial is not None, "Finance analyst should be denied salary access"


class TestReviewRLS:
    """Performance reviews follow similar rules to salary."""

    def test_contractor_denied_reviews(self):
        denial = check_tool_permission("hr_get_reviews", {"employee_id": 61}, CONTRACTOR)
        assert denial is not None, "Contractor should be denied review access"

    def test_ic_sees_own_reviews(self):
        from mcp_servers.hr.server import get_reviews
        result = get_reviews(IC_ENGINEER, employee_id=IC_ENGINEER.user_id)
        assert result.get("success"), "IC should see own reviews"

    def test_ic_cannot_see_others_reviews(self):
        denial = check_tool_permission("hr_get_reviews", {"employee_id": 1}, IC_ENGINEER)
        assert denial is not None, "IC should be denied others' reviews"


class TestTerminationRLS:
    """Termination records: HR and executive only."""

    def test_contractor_denied(self):
        denial = check_tool_permission("hr_get_terminations", {}, CONTRACTOR)
        assert denial is not None

    def test_ic_denied(self):
        denial = check_tool_permission("hr_get_terminations", {}, IC_ENGINEER)
        assert denial is not None

    def test_hr_allowed(self):
        denial = check_tool_permission("hr_get_terminations", {}, HR_PARTNER)
        assert denial is None

    def test_executive_allowed(self):
        denial = check_tool_permission("hr_get_terminations", {}, CEO)
        assert denial is None


class TestTicketRLS:
    """Ticket visibility follows team + ownership rules."""

    def test_ic_sees_own_team_tickets(self):
        from mcp_servers.tickets.server import search_tickets
        result = search_tickets(IC_ENGINEER, query="", limit=50)
        assert result.get("success")
        tickets = result.get("data", [])
        # All returned tickets should be: owned by user, assigned to user, or in user's team
        for t in tickets:
            is_own = t.get("owner_id") == IC_ENGINEER.user_id or t.get("assignee_id") == IC_ENGINEER.user_id
            is_team = t.get("team") in IC_ENGINEER.groups
            assert is_own or is_team, \
                f"IC saw ticket {t.get('id')} from team {t.get('team')} — not own or team"

    def test_contractor_does_not_see_hr_complaints(self):
        from mcp_servers.tickets.server import search_tickets
        result = search_tickets(CONTRACTOR, query="", limit=100)
        tickets = result.get("data", [])
        hr_complaints = [t for t in tickets if t.get("category") == "hr_complaint"
                         and t.get("owner_id") != CONTRACTOR.user_id
                         and t.get("assignee_id") != CONTRACTOR.user_id]
        # A contractor should not see hr_complaint tickets via team policy
        # (they may see their own if owner/assignee, which is fine)
        assert len(hr_complaints) == 0, \
            f"Contractor saw {len(hr_complaints)} HR complaint tickets via team access"


class TestDealRLS:
    """Deal access: owner, sales leadership, or executive."""

    def test_sales_rep_sees_own_deals(self):
        from mcp_servers.crm.server import search_deals
        result = search_deals(SALES_REP, query="", limit=50)
        assert result.get("success")
        deals = result.get("data", [])
        for d in deals:
            is_own = d.get("owner_id") == SALES_REP.user_id
            assert is_own, \
                f"Sales rep saw deal {d.get('id')} owned by {d.get('owner_id')}"

    def test_finance_denied_deal_details(self):
        denial = check_tool_permission("crm_get_deal", {}, FINANCE)
        assert denial is not None, "Finance should be denied deal access"

    def test_executive_sees_all_deals(self):
        from mcp_servers.crm.server import search_deals
        result = search_deals(CEO, query="", limit=200)
        assert result.get("success")
        # Executive should see more deals than a sales rep
        exec_count = len(result.get("data", []))
        rep_result = search_deals(SALES_REP, query="", limit=200)
        rep_count = len(rep_result.get("data", []))
        assert exec_count >= rep_count, \
            "Executive should see at least as many deals as a sales rep"


class TestChatRLS:
    """Chat channel access: public for all, private for members only."""

    def test_all_roles_see_public_channels(self):
        from mcp_servers.chat.server import list_channels
        for p in [CEO, IC_ENGINEER, CONTRACTOR, HR_PARTNER, SALES_REP]:
            result = list_channels(p)
            assert result.get("success"), f"{p.role} should see channels"
            channels = result.get("data", [])
            public = [c for c in channels if not c.get("is_private")]
            assert len(public) > 0, f"{p.role} should see public channels"


class TestCanaryDetection:
    """The output scanner must catch canary strings in responses."""

    def test_canary_pattern_matches(self):
        text = "Here is the data: CANARY-SAL-1234 and CANARY-TKT-5678"
        matches = CANARY_PATTERN.findall(text)
        assert len(matches) == 2
        assert "CANARY-SAL-1234" in matches
        assert "CANARY-TKT-5678" in matches

    def test_no_canary_in_clean_text(self):
        text = "The quarterly revenue was $2.3M, up 15% from last quarter."
        matches = CANARY_PATTERN.findall(text)
        assert len(matches) == 0


class TestCacheIsolation:
    """Response cache must never serve one user's cached data to another."""

    def test_cache_key_includes_user_and_role(self):
        from api.main import _cache_key_for
        # Same message, different users → different keys
        key_a = _cache_key_for(user_id=1, role="executive", message="Show my salary")
        key_b = _cache_key_for(user_id=22, role="individual_contributor", message="Show my salary")
        assert key_a != key_b, "Cache keys must differ for different users"

    def test_cache_key_includes_role(self):
        from api.main import _cache_key_for
        # Same user_id but different role → different keys
        key_a = _cache_key_for(user_id=1, role="executive", message="Show salaries")
        key_b = _cache_key_for(user_id=1, role="individual_contributor", message="Show salaries")
        assert key_a != key_b, "Cache keys must differ for different roles"

    def test_cache_key_deterministic(self):
        from api.main import _cache_key_for
        key1 = _cache_key_for(user_id=1, role="executive", message="Test query")
        key2 = _cache_key_for(user_id=1, role="executive", message="Test query")
        assert key1 == key2, "Same inputs must produce same cache key"

    def test_cache_key_normalizes_whitespace(self):
        from api.main import _cache_key_for
        key1 = _cache_key_for(user_id=1, role="executive", message="Show my salary")
        key2 = _cache_key_for(user_id=1, role="executive", message="  Show my salary  ")
        assert key1 == key2, "Cache key should normalize whitespace"


class TestGuardDenials:
    """Policy guards must deny unauthorized tool calls."""

    @pytest.mark.parametrize("tool,role_principal,should_deny", [
        ("hr_get_salary", CONTRACTOR, True),
        ("hr_get_reviews", CONTRACTOR, True),
        ("hr_get_leave", CONTRACTOR, True),
        ("hr_get_terminations", IC_ENGINEER, True),
        ("hr_get_terminations", SALES_REP, True),
        ("hr_get_terminations", HR_PARTNER, False),
        ("hr_get_terminations", CEO, False),
        ("crm_get_deal", FINANCE, True),
        ("crm_get_deal", SALES_REP, False),
        ("crm_get_deal", CEO, False),
    ])
    def test_guard_policy(self, tool, role_principal, should_deny):
        result = check_tool_permission(tool, {}, role_principal)
        if should_deny:
            assert result is not None, \
                f"{role_principal.role} should be denied {tool}"
        else:
            assert result is None, \
                f"{role_principal.role} should be allowed {tool}"
