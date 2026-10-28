"""Deterministic test: retrieval cache must not leak data across users.

This test verifies that the response cache key includes identity attributes
(user_id, role) so cached responses never cross security boundaries.

No database or LLM required — uses mocked tool calls.
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from company.principal import Principal

pytestmark = [pytest.mark.security]

CANARY_RE = re.compile(r"CANARY-[A-Z]+-\d{4}")

CEO = Principal(
    user_id=1, employee_id="MF-0001", role="executive",
    department="Executive", groups=["leadership", "board_access"],
)

CONTRACTOR = Principal(
    user_id=61, employee_id="MF-0061", role="contractor",
    department="Engineering", groups=["engineering", "engineering_all"],
)


class TestRetrievalCacheIsolation:
    """The retrieval cache must include identity attributes in the key.

    If this test fails, the cache is leaking data across security boundaries.
    """

    def test_contractor_does_not_get_executive_cached_results(self):
        """Simulate caching a salary lookup as CEO, then requesting as contractor.

        Uses the guard layer (check_tool_permission) to verify that even if
        results were cached, the contractor would be denied at the policy layer.
        Also verifies the cache key function differentiates users.
        """
        from agent.guards import check_tool_permission
        from api.main import _cache_key_for

        # CEO should be allowed salary access for employee 22
        ceo_denial = check_tool_permission(
            "hr_get_salary", {"employee_id": 22}, CEO
        )
        assert ceo_denial is None, "CEO should be allowed salary access"

        # Contractor must be denied salary access for employee 22
        contractor_denial = check_tool_permission(
            "hr_get_salary", {"employee_id": 22}, CONTRACTOR
        )
        assert contractor_denial is not None, (
            "POLICY LEAK: contractor was allowed salary access for employee 22!\n"
            "The guard layer must deny contractors from accessing salary data."
        )

        # Cache keys must differ for CEO vs contractor on same query
        ceo_key = _cache_key_for(
            user_id=CEO.user_id, role=CEO.role,
            message="Show salary for employee 22",
        )
        contractor_key = _cache_key_for(
            user_id=CONTRACTOR.user_id, role=CONTRACTOR.role,
            message="Show salary for employee 22",
        )
        assert ceo_key != contractor_key, (
            "CACHE LEAK: CEO and contractor get the same cache key!\n"
            "The cache key must include user_id and role to prevent cross-user leaks."
        )

    def test_different_roles_get_different_cache_keys(self):
        """Verify the cache key function differentiates by role."""
        from api.main import _cache_key_for

        key_exec = _cache_key_for(
            user_id=1, role="executive", message="Show salary for employee 22"
        )
        key_contractor = _cache_key_for(
            user_id=61, role="contractor", message="Show salary for employee 22"
        )
        assert key_exec != key_contractor, (
            "Cache keys for different roles must differ — "
            "otherwise cached results leak across security boundaries"
        )

    def test_same_user_same_query_hits_cache(self):
        """Same user + role + query should produce the same cache key."""
        from api.main import _cache_key_for

        key1 = _cache_key_for(user_id=1, role="executive", message="Show salary")
        key2 = _cache_key_for(user_id=1, role="executive", message="Show salary")
        assert key1 == key2, "Identical requests should produce the same cache key"

    def test_cache_key_is_case_insensitive(self):
        """Cache key must normalize case so 'Show Salary' == 'show salary'."""
        from api.main import _cache_key_for

        key1 = _cache_key_for(user_id=1, role="executive", message="Show Salary")
        key2 = _cache_key_for(user_id=1, role="executive", message="show salary")
        assert key1 == key2, "Cache key should be case-insensitive"
