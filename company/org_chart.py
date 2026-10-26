"""Generate a realistic org chart for Meridian Freight (120 employees)."""

import logging
import random
from dataclasses import dataclass, field

from faker import Faker

logger = logging.getLogger(__name__)

DEPARTMENTS = ["Sales", "Operations", "Finance", "HR", "Engineering"]

ROLE_TITLES: dict[str, dict[str, list[str]]] = {
    "Sales": {
        "executive": ["VP of Sales"],
        "manager": ["Sales Manager", "Regional Sales Lead"],
        "sales_rep": [
            "Account Executive",
            "Business Development Rep",
            "Senior Account Executive",
            "Enterprise Sales Rep",
        ],
        "individual_contributor": ["Sales Operations Analyst", "Sales Coordinator"],
        "contractor": ["Sales Consultant"],
    },
    "Operations": {
        "executive": ["VP of Operations"],
        "manager": ["Operations Manager", "Logistics Manager", "Dispatch Lead"],
        "individual_contributor": [
            "Logistics Coordinator",
            "Dispatch Specialist",
            "Route Planner",
            "Warehouse Supervisor",
            "Fleet Analyst",
            "Supply Chain Analyst",
        ],
        "contractor": ["Logistics Consultant", "Fleet Maintenance Contractor"],
    },
    "Finance": {
        "executive": ["CFO"],
        "manager": ["Finance Manager", "Accounting Lead"],
        "finance_analyst": [
            "Financial Analyst",
            "Senior Financial Analyst",
            "Budget Analyst",
            "Revenue Analyst",
        ],
        "individual_contributor": [
            "Accounts Payable Specialist",
            "Accounts Receivable Specialist",
            "Payroll Specialist",
        ],
        "contractor": ["External Auditor"],
    },
    "HR": {
        "executive": ["VP of People"],
        "manager": ["HR Manager"],
        "hr_partner": [
            "HR Business Partner",
            "Senior HR Partner",
            "Talent Acquisition Lead",
        ],
        "individual_contributor": [
            "HR Coordinator",
            "Benefits Administrator",
            "Recruiter",
        ],
        "contractor": ["HR Consultant"],
    },
    "Engineering": {
        "executive": ["CTO"],
        "manager": ["Engineering Manager", "Platform Lead", "DevOps Lead"],
        "individual_contributor": [
            "Software Engineer",
            "Senior Software Engineer",
            "Staff Engineer",
            "DevOps Engineer",
            "QA Engineer",
            "Data Engineer",
            "Systems Administrator",
        ],
        "contractor": ["Contract Developer", "Security Consultant"],
    },
}

# Target sizes per department (total ~120)
DEPT_SIZES = {
    "Sales": 22,
    "Operations": 35,
    "Finance": 18,
    "HR": 12,
    "Engineering": 28,
}

# CEO is separate, above all departments
# Add 5 for the C-suite/execs that are department heads


@dataclass
class PersonRecord:
    """An employee record before DB insertion."""

    first_name: str
    last_name: str
    email: str
    role: str
    title: str
    department: str
    manager_index: int | None  # index in the flat list
    hire_date: str
    is_active: bool = True
    groups: list[str] = field(default_factory=list)
    # Alternate name forms for deliberate inconsistency
    alt_names: list[str] = field(default_factory=list)


def generate_org_chart(seed: int = 42) -> list[PersonRecord]:
    """Generate 120 employees with a realistic org chart.

    Returns a flat list in insertion order (managers before reports).
    """
    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)

    people: list[PersonRecord] = []
    email_set: set[str] = set()

    def make_email(first: str, last: str) -> str:
        base = f"{first.lower()}.{last.lower()}@meridianfreight.com"
        email = base
        counter = 1
        while email in email_set:
            email = f"{first.lower()}.{last.lower()}{counter}@meridianfreight.com"
            counter += 1
        email_set.add(email)
        return email

    def make_hire_date() -> str:
        return fake.date_between(start_date="-8y", end_date="-3m").isoformat()

    def make_person(
        role: str,
        title: str,
        dept: str,
        manager_idx: int | None,
        *,
        groups: list[str] | None = None,
    ) -> int:
        first = fake.first_name()
        last = fake.last_name()
        email = make_email(first, last)

        # Create alternate name forms for deliberate inconsistency later
        alt_names = [
            f"{first[0]}. {last}",  # "J. Rivera"
            f"{first} {last[0]}.",  # "Jordan R."
        ]

        default_groups = [dept.lower(), f"{dept.lower()}_all"]
        if role == "executive":
            default_groups.append("leadership")
            default_groups.append("board_access")
        if role == "manager":
            default_groups.append("leadership")
        if role == "hr_partner":
            default_groups.append("hr_full_access")
        if role == "finance_analyst":
            default_groups.append("finance_read")

        p = PersonRecord(
            first_name=first,
            last_name=last,
            email=email,
            role=role,
            title=title,
            department=dept,
            manager_index=manager_idx,
            hire_date=make_hire_date(),
            groups=groups or default_groups,
            alt_names=alt_names,
        )
        people.append(p)
        return len(people) - 1

    # --- CEO ---
    ceo_idx = make_person(
        "executive",
        "CEO",
        "Operations",
        None,
        groups=["leadership", "board_access", "operations", "operations_all"],
    )

    # --- Department heads (executives) ---
    dept_head_indices: dict[str, int] = {}
    for dept in DEPARTMENTS:
        exec_titles = ROLE_TITLES[dept]["executive"]
        title = exec_titles[0]
        idx = make_person("executive", title, dept, ceo_idx)
        dept_head_indices[dept] = idx

    # --- Build each department ---
    for dept in DEPARTMENTS:
        head_idx = dept_head_indices[dept]
        target_size = DEPT_SIZES[dept]
        filled = 1  # head already counted

        # Managers reporting to department head
        manager_roles = ROLE_TITLES[dept].get("manager", [])
        manager_indices: list[int] = []
        for title in manager_roles:
            if filled >= target_size:
                break
            idx = make_person("manager", title, dept, head_idx)
            manager_indices.append(idx)
            filled += 1

        # If no managers, ICs report to head
        if not manager_indices:
            manager_indices = [head_idx]

        # Specialized roles
        for role_key in ["hr_partner", "finance_analyst", "sales_rep"]:
            if role_key not in ROLE_TITLES[dept]:
                continue
            titles = ROLE_TITLES[dept][role_key]
            for title in titles:
                if filled >= target_size - 2:  # leave room for contractors
                    break
                mgr = random.choice(manager_indices)
                make_person(role_key, title, dept, mgr)
                filled += 1

        # Individual contributors
        ic_titles = ROLE_TITLES[dept].get("individual_contributor", [])
        while filled < target_size - 1:  # leave 1 slot for contractor
            title = random.choice(ic_titles) if ic_titles else f"{dept} Specialist"
            mgr = random.choice(manager_indices)
            make_person("individual_contributor", title, dept, mgr)
            filled += 1

        # Contractors
        contractor_titles = ROLE_TITLES[dept].get("contractor", [])
        if contractor_titles and filled < target_size:
            title = random.choice(contractor_titles)
            mgr = random.choice(manager_indices)
            make_person("contractor", title, dept, mgr)
            filled += 1

    logger.info("Generated %d employees across %d departments", len(people), len(DEPARTMENTS))
    return people
