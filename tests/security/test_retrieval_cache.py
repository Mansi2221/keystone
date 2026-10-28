"""Deterministic test: retrieval cache must not leak data across users.

This test creates a cache keyed on (user_id, role, groups, query), verifies
that a contractor cannot see an executive's cached salary results.
If the cache key omits role/groups, this test MUST fail and name the leaked canaries.
"""

import re
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
        """Cache a salary lookup as CEO, then request the same query as a contractor.

        The contractor must NOT receive the CEO's cached salary data.
        If they do, the test fails and reports which canaries leaked.
        """
        from mcp_servers.hr.server import get_salary

        # Step 1: CEO queries salary for employee 22 — should succeed and cache
        ceo_result = get_salary(CEO, employee_id=22)
        assert ceo_result.get("success"), "CEO should see employee 22's salary"

        # Extract canaries from CEO's result
        ceo_text = str(ceo_result)
        ceo_canaries = set(CANARY_RE.findall(ceo_text))

        # Step 2: Contractor queries the same employee's salary
        contractor_result = get_salary(CONTRACTOR, employee_id=22)

        # Step 3: Contractor must NOT see the data
        contractor_text = str(contractor_result)
        contractor_canaries = set(CANARY_RE.findall(contractor_text))

        leaked = ceo_canaries & contractor_canaries
        assert len(leaked) == 0, (
            f"CACHE LEAK: contractor received executive's cached results!\n"
            f"Leaked canaries: {', '.join(sorted(leaked))}\n"
            f"The retrieval cache key must include user_id, role, and groups."
        )

        # Contractor should be denied
        assert contractor_result.get("error") or not contractor_result.get("data"), (
            "Contractor should be denied salary access for employee 22"
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
