"""Tests for org chart generation."""

import pytest

from company.org_chart import DEPARTMENTS, generate_org_chart


@pytest.mark.unit
class TestOrgChart:
    def test_employee_count(self, seed_data):
        """Should generate approximately 120 employees."""
        people = seed_data["people"]
        assert 115 <= len(people) <= 125, f"Expected ~120 employees, got {len(people)}"

    def test_all_departments_represented(self, seed_data):
        """Every department should have employees."""
        people = seed_data["people"]
        depts = {p.department for p in people}
        for dept in DEPARTMENTS:
            assert dept in depts, f"Department {dept} has no employees"

    def test_ceo_exists(self, seed_data):
        """There should be exactly one CEO with no manager."""
        people = seed_data["people"]
        ceos = [p for p in people if p.title == "CEO"]
        assert len(ceos) == 1
        assert ceos[0].manager_index is None

    def test_all_non_ceo_have_managers(self, seed_data):
        """Every employee except the CEO should have a manager."""
        people = seed_data["people"]
        for i, p in enumerate(people):
            if p.title == "CEO":
                continue
            assert p.manager_index is not None, f"Employee {p.first_name} {p.last_name} has no manager"

    def test_manager_indices_valid(self, seed_data):
        """Manager indices should reference existing employees earlier in the list."""
        people = seed_data["people"]
        for i, p in enumerate(people):
            if p.manager_index is not None:
                assert 0 <= p.manager_index < i, (
                    f"Employee {i} has invalid manager_index {p.manager_index}"
                )

    def test_roles_present(self, seed_data):
        """All expected roles should be present."""
        people = seed_data["people"]
        roles = {p.role for p in people}
        expected = {
            "executive", "manager", "individual_contributor",
            "hr_partner", "finance_analyst", "sales_rep", "contractor",
        }
        for role in expected:
            assert role in roles, f"Role {role} missing from org chart"

    def test_contractors_exist(self, seed_data):
        """There should be at least a few contractors."""
        people = seed_data["people"]
        contractors = [p for p in people if p.role == "contractor"]
        assert len(contractors) >= 3, f"Expected at least 3 contractors, got {len(contractors)}"

    def test_unique_emails(self, seed_data):
        """All employee emails should be unique."""
        people = seed_data["people"]
        emails = [p.email for p in people]
        assert len(emails) == len(set(emails))

    def test_reproducible(self):
        """Same seed should produce identical results."""
        people1 = generate_org_chart(seed=42)
        people2 = generate_org_chart(seed=42)
        assert len(people1) == len(people2)
        for a, b in zip(people1, people2):
            assert a.first_name == b.first_name
            assert a.last_name == b.last_name
            assert a.email == b.email

    def test_groups_populated(self, seed_data):
        """Every employee should have at least one group."""
        people = seed_data["people"]
        for p in people:
            assert len(p.groups) >= 1, f"{p.first_name} {p.last_name} has no groups"

    def test_executives_have_leadership_group(self, seed_data):
        """Executives should have 'leadership' in their groups."""
        people = seed_data["people"]
        execs = [p for p in people if p.role == "executive"]
        for e in execs:
            assert "leadership" in e.groups, f"Executive {e.full_name} lacks leadership group"

    def test_executives_have_board_access(self, seed_data):
        """Executives should have 'board_access' in their groups."""
        people = seed_data["people"]
        execs = [p for p in people if p.role == "executive"]
        for e in execs:
            assert "board_access" in e.groups, f"Executive {e.full_name} lacks board_access group"
