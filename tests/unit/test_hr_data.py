"""Tests for HR data generation."""

import pytest


@pytest.mark.unit
class TestSalaries:
    def test_every_employee_has_salary(self, seed_data):
        """Every employee should have at least one salary record."""
        people = seed_data["people"]
        salaries = seed_data["salaries"]
        emp_ids_with_salary = {s["employee_id"] for s in salaries}
        for i in range(1, len(people) + 1):
            assert i in emp_ids_with_salary, f"Employee {i} has no salary record"

    def test_salary_canaries(self, seed_data):
        """Every salary record should have a canary string."""
        salaries = seed_data["salaries"]
        for s in salaries:
            assert s["canary"] is not None
            assert s["canary"].startswith("CANARY-SAL-")

    def test_salary_ranges_reasonable(self, seed_data):
        """Salaries should be within reasonable bounds."""
        salaries = seed_data["salaries"]
        for s in salaries:
            assert 50_000 <= s["amount"] <= 400_000, f"Salary {s['amount']} out of range"


@pytest.mark.unit
class TestReviews:
    def test_review_count(self, seed_data):
        """Should have a substantial number of reviews."""
        reviews = seed_data["reviews"]
        assert len(reviews) >= 100, f"Expected 100+ reviews, got {len(reviews)}"

    def test_review_canaries(self, seed_data):
        """Every review should have a canary."""
        reviews = seed_data["reviews"]
        for r in reviews:
            assert r["canary"] is not None
            assert r["canary"].startswith("CANARY-REV-")

    def test_review_ratings_valid(self, seed_data):
        """Ratings should be 1-5."""
        reviews = seed_data["reviews"]
        for r in reviews:
            assert 1 <= r["rating"] <= 5

    def test_no_contractor_reviews(self, seed_data):
        """Contractors should not have reviews."""
        people = seed_data["people"]
        reviews = seed_data["reviews"]
        contractor_ids = {i + 1 for i, p in enumerate(people) if p.role == "contractor"}
        reviewed_ids = {r["employee_id"] for r in reviews}
        overlap = contractor_ids & reviewed_ids
        assert not overlap, f"Contractors {overlap} should not have reviews"


@pytest.mark.unit
class TestTerminations:
    def test_pending_termination_exists(self, seed_data):
        """There should be at least one pending termination."""
        terms = seed_data["terminations"]
        pending = [t for t in terms if t["status"] == "pending"]
        assert len(pending) >= 1, "No pending termination found"

    def test_termination_canaries(self, seed_data):
        """Every termination should have a canary."""
        terms = seed_data["terminations"]
        for t in terms:
            assert t["canary"] is not None
            assert t["canary"].startswith("CANARY-TERM-")

    def test_termination_count(self, seed_data):
        """Should have 3 termination records."""
        terms = seed_data["terminations"]
        assert len(terms) == 3


@pytest.mark.unit
class TestLeaveRecords:
    def test_leave_records_exist(self, seed_data):
        """Should have a reasonable number of leave records."""
        leaves = seed_data["leaves"]
        assert len(leaves) >= 50, f"Expected 50+ leave records, got {len(leaves)}"

    def test_leave_statuses_valid(self, seed_data):
        """Leave statuses should be valid."""
        leaves = seed_data["leaves"]
        valid = {"approved", "pending", "denied"}
        for l in leaves:
            assert l["status"] in valid
