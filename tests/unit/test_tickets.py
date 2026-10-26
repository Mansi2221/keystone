"""Tests for ticket data generation."""

import pytest


@pytest.mark.unit
class TestTickets:
    def test_ticket_count(self, seed_data):
        """Should generate ~2000 tickets."""
        tickets = seed_data["tickets"]
        assert len(tickets) == 2000

    def test_ticket_ids_unique(self, seed_data):
        """All ticket IDs should be unique."""
        tickets = seed_data["tickets"]
        ids = [t["ticket_id"] for t in tickets]
        assert len(ids) == len(set(ids))

    def test_security_incidents_exist(self, seed_data):
        """There should be security incident tickets."""
        tickets = seed_data["tickets"]
        security = [t for t in tickets if t["category"] == "security_incident"]
        assert len(security) >= 10, f"Expected 10+ security tickets, got {len(security)}"

    def test_hr_complaints_exist(self, seed_data):
        """There should be HR complaint tickets."""
        tickets = seed_data["tickets"]
        hr = [t for t in tickets if t["category"] == "hr_complaint"]
        assert len(hr) >= 5, f"Expected 5+ HR complaint tickets, got {len(hr)}"

    def test_restricted_tickets_have_canaries(self, seed_data):
        """Security and HR tickets should have canaries."""
        tickets = seed_data["tickets"]
        restricted = [
            t for t in tickets if t["category"] in ("security_incident", "hr_complaint")
        ]
        for t in restricted:
            assert t["canary"] is not None, f"Restricted ticket {t['ticket_id']} has no canary"
            assert t["canary"].startswith("CANARY-TKT-")

    def test_regular_tickets_no_canaries(self, seed_data):
        """Regular tickets should not have canaries."""
        tickets = seed_data["tickets"]
        regular = [
            t for t in tickets if t["category"] in ("it", "ops")
        ]
        for t in regular:
            assert t["canary"] is None, f"Regular ticket {t['ticket_id']} should not have canary"

    def test_comments_exist(self, seed_data):
        """Should generate comments for tickets."""
        comments = seed_data["comments"]
        assert len(comments) >= 1000, f"Expected 1000+ comments, got {len(comments)}"

    def test_valid_statuses(self, seed_data):
        """Ticket statuses should be valid."""
        tickets = seed_data["tickets"]
        valid = {"open", "in_progress", "resolved", "closed"}
        for t in tickets:
            assert t["status"] in valid

    def test_valid_priorities(self, seed_data):
        """Ticket priorities should be valid."""
        tickets = seed_data["tickets"]
        valid = {"low", "medium", "high", "critical"}
        for t in tickets:
            assert t["priority"] in valid
