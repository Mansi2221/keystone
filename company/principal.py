"""Principal model representing the authenticated user making a request.

The principal is always set by the gateway from the JWT token and HR system.
It is never accepted from the LLM or chosen by the model.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """Identity and authorization context for the current request."""

    user_id: int
    employee_id: str
    role: str
    department: str
    groups: list[str] = field(default_factory=list)
    manager_id: int | None = None
    # IDs of all direct and indirect reports
    report_ids: list[int] = field(default_factory=list)

    def has_group(self, group: str) -> bool:
        return group in self.groups

    def is_executive(self) -> bool:
        return self.role == "executive"

    def is_manager(self) -> bool:
        return self.role == "manager"

    def is_hr_partner(self) -> bool:
        return self.role == "hr_partner"

    def is_contractor(self) -> bool:
        return self.role == "contractor"

    def can_see_own(self, resource_employee_id: int) -> bool:
        """Check if this resource belongs to the principal."""
        return self.user_id == resource_employee_id

    def can_see_report(self, resource_employee_id: int) -> bool:
        """Check if this resource belongs to a direct/indirect report."""
        return resource_employee_id in self.report_ids
