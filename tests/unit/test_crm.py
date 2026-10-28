"""Tests for CRM data generation."""

import pytest


@pytest.mark.unit
class TestCRM:
    def test_customer_count(self, seed_data):
        """Should generate 80 customers."""
        customers = seed_data["customers"]
        assert len(customers) == 80

    def test_deal_count(self, seed_data):
        """Should generate 150 deals."""
        deals = seed_data["deals"]
        assert len(deals) == 150

    def test_deal_ids_unique(self, seed_data):
        """All deal IDs should be unique."""
        deals = seed_data["deals"]
        ids = [d["deal_id"] for d in deals]
        assert len(ids) == len(set(ids))

    def test_all_deals_have_canaries(self, seed_data):
        """Every deal should have a canary (all deals are restricted)."""
        deals = seed_data["deals"]
        for d in deals:
            assert d["canary"] is not None, f"Deal {d['deal_id']} has no canary"
            assert d["canary"].startswith("CANARY-DEAL-")

    def test_deal_values_positive(self, seed_data):
        """All deal values should be positive."""
        deals = seed_data["deals"]
        for d in deals:
            assert d["value"] > 0

    def test_valid_stages(self, seed_data):
        """Deal stages should be valid."""
        deals = seed_data["deals"]
        valid = {
            "prospecting",
            "qualification",
            "proposal",
            "negotiation",
            "closed_won",
            "closed_lost",
        }
        for d in deals:
            assert d["stage"] in valid

    def test_deals_reference_valid_customers(self, seed_data):
        """Deals should reference valid customer IDs."""
        customers = seed_data["customers"]
        deals = seed_data["deals"]
        for d in deals:
            assert 1 <= d["customer_id"] <= len(customers)
