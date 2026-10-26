"""Tests for canary registry completeness."""

import pytest

from company.canary import CANARY_PREFIXES


@pytest.mark.unit
class TestCanaryRegistry:
    def test_canary_count(self, seed_data):
        """Should have a substantial number of canaries."""
        canary_gen = seed_data["canary_gen"]
        # Salaries + reviews + terminations + restricted tickets + restricted docs
        # + restricted messages + all deals
        assert canary_gen.count >= 300, f"Expected 300+ canaries, got {canary_gen.count}"

    def test_canaries_unique(self, seed_data):
        """All canary strings should be unique."""
        canary_gen = seed_data["canary_gen"]
        canaries = [e.canary for e in canary_gen.entries]
        assert len(canaries) == len(set(canaries)), "Duplicate canaries found"

    def test_all_resource_types_present(self, seed_data):
        """Canaries should cover all resource types."""
        canary_gen = seed_data["canary_gen"]
        types = {e.resource_type for e in canary_gen.entries}
        expected = {"salary", "review", "termination", "ticket", "document", "message", "deal"}
        for t in expected:
            assert t in types, f"No canary for resource type '{t}'"

    def test_canary_format(self, seed_data):
        """All canaries should follow the CANARY-PREFIX-NNNN format."""
        canary_gen = seed_data["canary_gen"]
        valid_prefixes = set(CANARY_PREFIXES.values())
        for entry in canary_gen.entries:
            parts = entry.canary.rsplit("-", 1)
            assert len(parts) == 2, f"Invalid canary format: {entry.canary}"
            prefix = parts[0]
            suffix = parts[1]
            assert prefix in valid_prefixes, f"Unknown prefix in {entry.canary}"
            assert suffix.isdigit() and len(suffix) == 4, f"Invalid suffix in {entry.canary}"

    def test_every_salary_has_canary(self, seed_data):
        """Every salary record's canary should be in the registry."""
        salaries = seed_data["salaries"]
        canary_gen = seed_data["canary_gen"]
        registry_canaries = {e.canary for e in canary_gen.entries}
        for s in salaries:
            assert s["canary"] in registry_canaries, f"Salary canary {s['canary']} not registered"

    def test_every_deal_has_canary(self, seed_data):
        """Every deal's canary should be in the registry."""
        deals = seed_data["deals"]
        canary_gen = seed_data["canary_gen"]
        registry_canaries = {e.canary for e in canary_gen.entries}
        for d in deals:
            assert d["canary"] in registry_canaries, f"Deal canary {d['canary']} not registered"

    def test_canary_entries_have_permissions(self, seed_data):
        """Every canary entry should have a required permission."""
        canary_gen = seed_data["canary_gen"]
        for entry in canary_gen.entries:
            assert entry.required_permission, f"Canary {entry.canary} has no permission"

    def test_canary_entries_have_allowed_roles(self, seed_data):
        """Every canary entry should have allowed roles or employee IDs."""
        canary_gen = seed_data["canary_gen"]
        for entry in canary_gen.entries:
            has_roles = len(entry.allowed_roles) > 0
            has_ids = len(entry.allowed_employee_ids) > 0
            assert has_roles or has_ids, (
                f"Canary {entry.canary} has no allowed roles or employee IDs"
            )

    def test_restricted_records_match_canaries(self, seed_data):
        """Count of restricted records should match canary count per type."""
        canary_gen = seed_data["canary_gen"]

        # Count canaries by type
        type_counts: dict[str, int] = {}
        for entry in canary_gen.entries:
            type_counts[entry.resource_type] = type_counts.get(entry.resource_type, 0) + 1

        # Verify salaries: every salary has a canary
        assert type_counts.get("salary", 0) == len(seed_data["salaries"])

        # Verify deals: every deal has a canary
        assert type_counts.get("deal", 0) == len(seed_data["deals"])

        # Verify terminations: every termination has a canary
        assert type_counts.get("termination", 0) == len(seed_data["terminations"])
