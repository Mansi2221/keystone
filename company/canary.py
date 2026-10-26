"""Canary string generation and registry management.

Every restricted record gets a unique canary string like CANARY-HR-4471.
The canary registry tracks which canaries exist, what they protect,
and which roles/users are permitted to see them.
"""

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Prefixes by resource type
CANARY_PREFIXES = {
    "salary": "CANARY-SAL",
    "review": "CANARY-REV",
    "termination": "CANARY-TERM",
    "ticket": "CANARY-TKT",
    "document": "CANARY-DOC",
    "message": "CANARY-MSG",
    "deal": "CANARY-DEAL",
}


@dataclass
class CanaryEntry:
    """A canary to be registered."""

    canary: str
    resource_type: str
    resource_id: int
    required_permission: str
    allowed_roles: list[str]
    allowed_employee_ids: list[int]
    description: str


class CanaryGenerator:
    """Generates unique canary strings and tracks them for registry insertion."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._used: set[str] = set()
        self.entries: list[CanaryEntry] = []

    def generate(
        self,
        resource_type: str,
        resource_id: int,
        required_permission: str,
        allowed_roles: list[str],
        allowed_employee_ids: list[int] | None = None,
        description: str = "",
    ) -> str:
        """Generate a unique canary string and register it."""
        prefix = CANARY_PREFIXES.get(resource_type, "CANARY-UNK")
        while True:
            suffix = self._rng.randint(1000, 9999)
            canary = f"{prefix}-{suffix}"
            if canary not in self._used:
                break

        self._used.add(canary)
        self.entries.append(
            CanaryEntry(
                canary=canary,
                resource_type=resource_type,
                resource_id=resource_id,
                required_permission=required_permission,
                allowed_roles=allowed_roles,
                allowed_employee_ids=allowed_employee_ids or [],
                description=description,
            )
        )
        return canary

    @property
    def count(self) -> int:
        return len(self.entries)
