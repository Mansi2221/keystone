"""Tests for chat data generation."""

import pytest


@pytest.mark.unit
class TestChat:
    def test_message_count(self, seed_data):
        """Should generate ~5000 messages."""
        messages = seed_data["messages"]
        assert len(messages) >= 4900, f"Expected ~5000 messages, got {len(messages)}"

    def test_channels_exist(self, seed_data):
        """Should have public, private, and DM channels."""
        channels = seed_data["channels"]
        public = [c for c in channels if not c["is_private"]]
        private = [c for c in channels if c["is_private"] and not c["is_dm"]]
        dms = [c for c in channels if c["is_dm"]]

        assert len(public) >= 10
        assert len(private) >= 3
        assert len(dms) >= 5

    def test_leadership_channel_exists(self, seed_data):
        """The private leadership channel should exist."""
        channels = seed_data["channels"]
        leadership = [c for c in channels if c["name"] == "leadership-team"]
        assert len(leadership) == 1
        assert leadership[0]["is_private"] is True

    def test_layoff_dm_exists(self, seed_data):
        """The layoff discussion DM should exist."""
        channels = seed_data["channels"]
        layoff_dms = [c for c in channels if c["name"] == "dm-layoff-discussion"]
        assert len(layoff_dms) == 1
        assert layoff_dms[0]["is_dm"] is True

    def test_private_messages_have_canaries(self, seed_data):
        """Some private/DM messages should have canaries."""
        messages = seed_data["messages"]
        canary_msgs = [m for m in messages if m["canary"] is not None]
        assert len(canary_msgs) >= 6, f"Expected 6+ canary messages, got {len(canary_msgs)}"

    def test_all_messages_have_authors(self, seed_data):
        """Every message should have a valid author."""
        messages = seed_data["messages"]
        people = seed_data["people"]
        valid_ids = set(range(1, len(people) + 1))
        for m in messages:
            assert m["author_id"] in valid_ids

    def test_members_assigned(self, seed_data):
        """Channel members should be assigned."""
        members = seed_data["members"]
        assert len(members) >= 500
