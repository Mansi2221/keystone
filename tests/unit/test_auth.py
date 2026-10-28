"""Unit tests for JWT auth and principal resolution."""

import pytest

from api.auth import create_access_token, decode_token, get_demo_users
from company.principal import Principal


@pytest.mark.unit
class TestJWT:
    def test_create_and_decode_token(self):
        """Creating and decoding a token should round-trip."""
        token = create_access_token(42)
        payload = decode_token(token)
        assert payload["sub"] == "42"

    def test_demo_users_defined(self):
        """All expected demo roles should be present (requires seeded DB)."""
        demo_users = get_demo_users()
        if not demo_users:
            pytest.skip("No demo users available (DB not seeded)")
        roles = {info["role"] for info in demo_users.values()}
        assert "executive" in roles
        assert "manager" in roles
        assert "hr_partner" in roles
        assert "finance_analyst" in roles
        assert "sales_rep" in roles
        assert "individual_contributor" in roles
        assert "contractor" in roles

    def test_demo_users_have_employee_ids(self):
        """Every demo user should have a positive employee ID."""
        demo_users = get_demo_users()
        if not demo_users:
            pytest.skip("No demo users available (DB not seeded)")
        for key, info in demo_users.items():
            assert info["employee_id"] > 0, f"Demo user {key} has invalid employee_id"


@pytest.mark.unit
class TestPrincipal:
    def test_principal_is_executive(self):
        p = Principal(user_id=1, employee_id="MF-0001", role="executive", department="Operations")
        assert p.is_executive()
        assert not p.is_contractor()

    def test_principal_is_contractor(self):
        p = Principal(user_id=99, employee_id="MF-0099", role="contractor", department="Engineering")
        assert p.is_contractor()
        assert not p.is_executive()

    def test_can_see_own(self):
        p = Principal(user_id=5, employee_id="MF-0005", role="individual_contributor", department="Engineering")
        assert p.can_see_own(5)
        assert not p.can_see_own(6)

    def test_can_see_report(self):
        p = Principal(
            user_id=10, employee_id="MF-0010", role="manager",
            department="Sales", report_ids=[20, 21, 22],
        )
        assert p.can_see_report(20)
        assert not p.can_see_report(30)

    def test_has_group(self):
        p = Principal(
            user_id=1, employee_id="MF-0001", role="executive",
            department="Operations", groups=["leadership", "board_access"],
        )
        assert p.has_group("leadership")
        assert not p.has_group("hr_full_access")
