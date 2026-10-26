"""Input and output guards for the agent.

Input guard: scans retrieved content for prompt injection patterns.
Output scanner: scans responses for canary strings and sensitive patterns.
"""

import logging
import re
from typing import Any

from company.database import SessionLocal
from company.models import CanaryRecord
from company.principal import Principal
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Prompt injection detection patterns
INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?previous\s+instructions",
    r"(?i)system\s+override",
    r"(?i)\|im_start\|",
    r"(?i)admin\s+mode",
    r"(?i)bypass[_ ]rls",
    r"(?i)jailbreak",
    r"(?i)role[_ ]escalation",
    r"(?i)ignore\s+permission",
    r"(?i)ignore\s+access\s+control",
    r"(?i)reveal\s+all\s+(?:salary|salaries|confidential)",
    r"(?i)show\s+all\s+restricted",
    r"(?i)debug\s+mode",
    r"(?i)priority\s+override",
    r"(?i)begin\s+override",
    r"(?i)treat\s+all\s+users\s+as\s+executive",
    r"(?i)set\s+current_user\.role",
]

# Compiled patterns for performance
_INJECTION_COMPILED = [re.compile(p) for p in INJECTION_PATTERNS]

# Canary pattern
CANARY_PATTERN = re.compile(r"CANARY-[A-Z]+-\d{4}")

# Sensitive patterns (beyond canaries)
SENSITIVE_PATTERNS = [
    re.compile(r"\$\d{2,3},?\d{3}"),  # Dollar amounts like $125,000
    re.compile(r"(?i)salary\s*(?:of|for|:)\s*\$"),  # "salary of $..."
    re.compile(r"(?i)termination.*pending", re.DOTALL),
    re.compile(r"(?i)acquisition.*(?:NorthStar|Pacific Coast)", re.DOTALL),
]


def scan_for_injections(content: str) -> list[str]:
    """Scan content for prompt injection patterns.

    Returns a list of detected injection types. Empty list means clean.
    """
    flags: list[str] = []
    for pattern in _INJECTION_COMPILED:
        if pattern.search(content):
            flags.append(f"injection_detected:{pattern.pattern[:50]}")
    return flags


def wrap_untrusted(content: str, source: str = "tool_result") -> str:
    """Wrap retrieved content as untrusted data before passing to the model.

    This marks the boundaries of external data so the model knows not to
    treat it as instructions.
    """
    return (
        f"<untrusted_data source=\"{source}\">\n"
        f"{content}\n"
        f"</untrusted_data>"
    )


def scan_output_for_leaks(
    response: str,
    principal: Principal,
) -> list[str]:
    """Scan agent output for canary strings or sensitive data the user shouldn't see.

    Returns a list of leak descriptions. Empty list means clean.
    """
    flags: list[str] = []

    # Check for canary strings
    canaries_found = CANARY_PATTERN.findall(response)
    if canaries_found:
        # Look up each canary in the registry
        session = SessionLocal()
        try:
            for canary_str in canaries_found:
                record = session.execute(
                    select(CanaryRecord).where(CanaryRecord.canary == canary_str)
                ).scalar_one_or_none()

                if record is None:
                    # Unknown canary — flag it
                    flags.append(f"unknown_canary:{canary_str}")
                    continue

                # Check if user is allowed
                role_allowed = principal.role in record.allowed_roles
                id_allowed = principal.user_id in (record.allowed_employee_ids or [])

                if not role_allowed and not id_allowed:
                    flags.append(
                        f"canary_leak:{canary_str}|"
                        f"resource={record.resource_type}:{record.resource_id}|"
                        f"required={record.required_permission}"
                    )
        finally:
            session.close()

    return flags


def check_aggregation_risk(
    tool_name: str,
    arguments: dict[str, Any],
    principal: Principal,
) -> str | None:
    """Check for aggregation leak risks.

    Example: asking for average salary of a team with fewer than 5 members
    would effectively reveal individual salaries.
    """
    # If asking for salary data with aggregation intent
    if tool_name == "hr_get_salary" and principal.role == "manager":
        # Manager can see reports, but if team < 5, aggregation leaks individuals
        if len(principal.report_ids) < 5:
            return (
                "Aggregation risk: team size is too small for anonymous aggregation. "
                "Salary data for teams with fewer than 5 members cannot be aggregated "
                "without revealing individual values."
            )
    return None
