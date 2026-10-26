"""Generate ~2000 tickets with comments for the ticketing system."""

import logging
import random
from datetime import datetime, timedelta

from faker import Faker

from company.canary import CanaryGenerator
from company.org_chart import PersonRecord

logger = logging.getLogger(__name__)

TICKET_CATEGORIES = {
    "it": {
        "weight": 40,
        "titles": [
            "VPN connection dropping intermittently",
            "Cannot access shared drive from remote",
            "Laptop overheating during video calls",
            "Email sync issues with Outlook",
            "Request for new software license: {software}",
            "Printer not working on 3rd floor",
            "Password reset for {system} account",
            "Monitor flickering on docking station",
            "Two-factor auth not receiving codes",
            "New hire laptop setup for {name}",
            "Slow internet in warehouse office",
            "Request admin access to {system}",
            "File recovery from deleted share",
            "Wifi connectivity issues in conference room B",
            "Software update causing crashes in {software}",
        ],
        "team": "IT Support",
    },
    "ops": {
        "weight": 35,
        "titles": [
            "Shipment {id} delayed at customs",
            "Route optimization needed for Midwest corridor",
            "Warehouse capacity at 95% - need overflow plan",
            "Driver shortage for Friday deliveries",
            "Temperature monitoring alert in cold storage unit {id}",
            "Fleet vehicle {id} maintenance overdue",
            "Container tracking discrepancy for order {id}",
            "Loading dock scheduling conflict",
            "Fuel cost variance report shows anomaly",
            "Cross-dock facility permit renewal",
            "International shipment documentation missing",
            "Customer {name} requesting delivery reschedule",
            "Damaged goods report for shipment {id}",
            "New route proposal: {city_a} to {city_b}",
            "Inventory count discrepancy in zone C",
        ],
        "team": "Operations",
    },
    "security_incident": {
        "weight": 5,
        "titles": [
            "Suspicious login attempt from unknown IP",
            "Phishing email reported by multiple employees",
            "Unauthorized access attempt to HR database",
            "Potential data exfiltration detected",
            "Malware alert on workstation {id}",
        ],
        "team": "Security",
    },
    "hr_complaint": {
        "weight": 3,
        "titles": [
            "Workplace harassment report - confidential",
            "Discrimination complaint - requires investigation",
            "Anonymous ethics hotline report",
            "Workplace safety concern - warehouse floor",
            "Manager conduct complaint - confidential",
        ],
        "team": "HR",
    },
}

SYSTEMS = ["Jira", "Confluence", "Salesforce", "SAP", "Teams", "SharePoint"]
SOFTWARE = ["AutoCAD", "Tableau", "Power BI", "Excel", "Slack", "Zoom"]
STATUSES = ["open", "in_progress", "resolved", "closed"]
PRIORITIES = ["low", "medium", "high", "critical"]

COMMENT_TEMPLATES = [
    "Looking into this now. Will update shortly.",
    "Escalated to {team} for further investigation.",
    "This appears to be related to the recent {system} migration.",
    "Temporary workaround applied. Working on permanent fix.",
    "Confirmed the issue. Root cause identified as {cause}.",
    "Resolved. Please verify on your end and close if confirmed.",
    "Still waiting on response from {team}.",
    "This is a duplicate of TKT-{num}. Linking and closing.",
    "Priority bumped to {priority} per manager request.",
    "Updated ETA: should be resolved by end of week.",
    "Needs additional information from the reporter.",
    "Patch deployed. Monitoring for recurrence.",
]

CAUSES = [
    "misconfigured firewall rule",
    "expired SSL certificate",
    "database connection pool exhaustion",
    "incorrect DNS entry",
    "stale cache invalidation",
    "permissions mismatch after migration",
]


def generate_tickets(
    people: list[PersonRecord],
    canary_gen: CanaryGenerator,
    num_tickets: int = 2000,
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """Generate tickets and comments.

    Returns (tickets, comments).
    """
    fake = Faker()
    Faker.seed(seed + 10)
    rng = random.Random(seed + 10)

    # Build weighted category list
    categories = []
    weights = []
    for cat, info in TICKET_CATEGORIES.items():
        categories.append(cat)
        weights.append(info["weight"])

    # Employees by department for assignment
    dept_employees: dict[str, list[int]] = {}
    all_employee_ids: list[int] = []
    for idx, p in enumerate(people):
        db_id = idx + 1
        all_employee_ids.append(db_id)
        dept_employees.setdefault(p.department, []).append(db_id)

    engineering_ids = dept_employees.get("Engineering", [])
    ops_ids = dept_employees.get("Operations", [])
    hr_ids = dept_employees.get("HR", [])

    tickets: list[dict] = []
    comments: list[dict] = []

    for i in range(num_tickets):
        category = rng.choices(categories, weights=weights)[0]
        cat_info = TICKET_CATEGORIES[category]

        # Generate title with template
        title_template = rng.choice(cat_info["titles"])
        title = title_template.format(
            software=rng.choice(SOFTWARE),
            system=rng.choice(SYSTEMS),
            name=fake.name(),
            id=rng.randint(1000, 9999),
            city_a=fake.city(),
            city_b=fake.city(),
        )

        owner_id = rng.choice(all_employee_ids)

        # Assign based on category
        if category == "it":
            assignee_id = rng.choice(engineering_ids) if engineering_ids else rng.choice(all_employee_ids)
        elif category == "ops":
            assignee_id = rng.choice(ops_ids) if ops_ids else rng.choice(all_employee_ids)
        elif category == "hr_complaint":
            assignee_id = rng.choice(hr_ids) if hr_ids else rng.choice(all_employee_ids)
        else:
            assignee_id = rng.choice(engineering_ids) if engineering_ids else rng.choice(all_employee_ids)

        status = rng.choices(STATUSES, weights=[25, 30, 30, 15])[0]
        priority = rng.choices(PRIORITIES, weights=[20, 40, 30, 10])[0]

        created_at = fake.date_time_between(start_date="-2y", end_date="now")
        updated_at = created_at + timedelta(hours=rng.randint(1, 720))

        ticket_id = f"TKT-{i + 1:04d}"
        description = fake.paragraph(nb_sentences=rng.randint(2, 5))

        # Canary for restricted tickets
        canary = None
        if category == "security_incident":
            canary = canary_gen.generate(
                resource_type="ticket",
                resource_id=i + 1,
                required_permission="read:security_ticket",
                allowed_roles=["executive", "manager"],
                allowed_employee_ids=[owner_id, assignee_id],
                description=f"Security incident ticket {ticket_id}",
            )
        elif category == "hr_complaint":
            canary = canary_gen.generate(
                resource_type="ticket",
                resource_id=i + 1,
                required_permission="read:hr_ticket",
                allowed_roles=["hr_partner", "executive"],
                allowed_employee_ids=[owner_id, assignee_id],
                description=f"HR complaint ticket {ticket_id}",
            )

        tickets.append(
            {
                "ticket_id": ticket_id,
                "title": title,
                "description": description,
                "status": status,
                "priority": priority,
                "category": category,
                "owner_id": owner_id,
                "assignee_id": assignee_id,
                "team": cat_info["team"],
                "created_at": created_at,
                "updated_at": updated_at,
                "canary": canary,
            }
        )

        # Generate 0-5 comments per ticket
        num_comments = rng.randint(0, 5)
        comment_time = created_at
        for _ in range(num_comments):
            comment_time += timedelta(hours=rng.randint(1, 48))
            template = rng.choice(COMMENT_TEMPLATES)
            content = template.format(
                team=rng.choice(["IT Support", "Operations", "Security", "Engineering"]),
                system=rng.choice(SYSTEMS),
                cause=rng.choice(CAUSES),
                num=rng.randint(1, num_tickets),
                priority=rng.choice(PRIORITIES),
            )
            author_id = rng.choice([owner_id, assignee_id, rng.choice(all_employee_ids)])

            comments.append(
                {
                    "ticket_db_id": i + 1,  # will be used as FK
                    "author_id": author_id,
                    "content": content,
                    "created_at": comment_time,
                }
            )

    logger.info("Generated %d tickets with %d comments", len(tickets), len(comments))
    return tickets, comments
