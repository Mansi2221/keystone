"""Unit tests for v5 fixes: scoring, output scanner, guards.

All tests use mocked data — no database or LLM required.
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from company.principal import Principal
from agent.guards import (
    CANARY_PATTERN,
    check_tool_permission,
    redact_canary_leaks,
    scan_output_for_leaks,
)

pytestmark = pytest.mark.unit


# ── Test Principals ─────────────────────────────────────────────

IC = Principal(
    user_id=22, employee_id="MF-0022", role="individual_contributor",
    department="Engineering", groups=["engineering"],
)

CONTRACTOR = Principal(
    user_id=61, employee_id="MF-0061", role="contractor",
    department="Engineering", groups=["engineering"],
)

HR = Principal(
    user_id=5, employee_id="MF-0005", role="hr_partner",
    department="HR", groups=["hr"],
)

CEO = Principal(
    user_id=1, employee_id="MF-0001", role="executive",
    department="Executive", groups=["leadership"],
)


def _mock_canary_record(canary: str, resource_type: str, resource_id: int,
                         allowed_roles: list, allowed_employee_ids: list | None = None):
    record = MagicMock()
    record.canary = canary
    record.resource_type = resource_type
    record.resource_id = resource_id
    record.allowed_roles = allowed_roles
    record.allowed_employee_ids = allowed_employee_ids or []
    record.required_permission = f"view_{resource_type}"
    return record


class TestOutputScannerOwnSalary:
    """Own salary canaries should not be flagged as leaks."""

    @patch("agent.guards.SessionLocal")
    def test_own_salary_not_flagged(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        # Canary for IC's own salary (resource_id == user_id)
        record = _mock_canary_record(
            "CANARY-SAL-1234", "salary", 22,
            allowed_roles=["hr_partner", "executive"],
        )
        session.execute.return_value.scalar_one_or_none.return_value = record

        flags = scan_output_for_leaks("Your salary is $96,000. CANARY-SAL-1234", IC)
        assert len(flags) == 0, "Own salary canary should not be flagged"

    @patch("agent.guards.SessionLocal")
    def test_other_salary_flagged(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        # Canary for someone else's salary (resource_id != user_id)
        record = _mock_canary_record(
            "CANARY-SAL-5678", "salary", 99,
            allowed_roles=["hr_partner", "executive"],
        )
        session.execute.return_value.scalar_one_or_none.return_value = record

        flags = scan_output_for_leaks("Employee 99 salary CANARY-SAL-5678", IC)
        assert len(flags) == 1, "Other person's salary canary should be flagged"


class TestOutputScannerUnknownCanary:
    """Unknown canaries (not in registry) should not be flagged."""

    @patch("agent.guards.SessionLocal")
    def test_unknown_canary_skipped(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.execute.return_value.scalar_one_or_none.return_value = None

        flags = scan_output_for_leaks("Deal: CANARY-DEAL-9999", IC)
        assert len(flags) == 0, "Unknown canary should be silently skipped"


class TestCanaryRedaction:
    """The redaction function must remove unauthorized canaries from output."""

    @patch("agent.guards.SessionLocal")
    def test_redacts_unauthorized_canary(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        record = _mock_canary_record(
            "CANARY-SAL-5678", "salary", 99,
            allowed_roles=["hr_partner", "executive"],
        )
        session.execute.return_value.scalar_one_or_none.return_value = record

        original = "The salary is $150,000 CANARY-SAL-5678 for that employee."
        cleaned, redacted = redact_canary_leaks(original, IC)

        assert "CANARY-SAL-5678" not in cleaned
        assert "[REDACTED]" in cleaned
        assert "CANARY-SAL-5678" in redacted

    @patch("agent.guards.SessionLocal")
    def test_preserves_authorized_canary(self, mock_session_cls):
        session = MagicMock()
        mock_session_cls.return_value = session

        record = _mock_canary_record(
            "CANARY-SAL-1234", "salary", 22,
            allowed_roles=["hr_partner", "executive"],
        )
        session.execute.return_value.scalar_one_or_none.return_value = record

        original = "Your salary: CANARY-SAL-1234"
        cleaned, redacted = redact_canary_leaks(original, IC)

        assert "CANARY-SAL-1234" in cleaned
        assert len(redacted) == 0


class TestTicketGuard:
    """HR complaint tickets must be restricted to HR and executives."""

    def test_ic_denied_hr_complaint_tickets(self):
        denial = check_tool_permission(
            "tickets_search", {"category": "hr_complaint"}, IC
        )
        assert denial is not None, "IC should be denied HR complaint ticket search"

    def test_contractor_denied_hr_complaint_tickets(self):
        denial = check_tool_permission(
            "tickets_search", {"category": "hr_complaint"}, CONTRACTOR
        )
        assert denial is not None

    def test_hr_allowed_hr_complaint_tickets(self):
        denial = check_tool_permission(
            "tickets_search", {"category": "hr_complaint"}, HR
        )
        assert denial is None, "HR should be allowed HR complaint ticket search"

    def test_executive_allowed_hr_complaint_tickets(self):
        denial = check_tool_permission(
            "tickets_search", {"category": "hr_complaint"}, CEO
        )
        assert denial is None

    def test_ic_allowed_normal_tickets(self):
        denial = check_tool_permission(
            "tickets_search", {"category": "bug"}, IC
        )
        assert denial is None, "IC should be allowed normal ticket search"


class TestCanaryPattern:
    """The canary regex must match the expected format."""

    def test_matches_standard_canaries(self):
        assert CANARY_PATTERN.search("CANARY-SAL-1234")
        assert CANARY_PATTERN.search("CANARY-TKT-5678")
        assert CANARY_PATTERN.search("CANARY-REV-9012")
        assert CANARY_PATTERN.search("CANARY-DEAL-3456")
        assert CANARY_PATTERN.search("CANARY-MSG-7890")

    def test_no_false_positives(self):
        assert not CANARY_PATTERN.search("The canary in the coal mine")
        assert not CANARY_PATTERN.search("CANARY-test-abc")
        assert not CANARY_PATTERN.search("Revenue was $125,000")
