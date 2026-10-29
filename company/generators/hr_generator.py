"""Generate HR data: salaries, performance reviews, leave records, terminations."""

import logging
import random
from datetime import date, timedelta

from faker import Faker

from company.canary import CanaryGenerator
from company.org_chart import PersonRecord

logger = logging.getLogger(__name__)

# Base salary ranges by role
SALARY_RANGES: dict[str, tuple[int, int]] = {
    "executive": (180_000, 350_000),
    "manager": (120_000, 200_000),
    "hr_partner": (90_000, 140_000),
    "finance_analyst": (85_000, 130_000),
    "sales_rep": (70_000, 120_000),
    "individual_contributor": (65_000, 130_000),
    "contractor": (80_000, 160_000),
}

REVIEW_SUMMARIES = [
    "Consistently exceeds expectations. Strong leadership and communication skills.",
    "Meets expectations. Solid performance with room for growth in strategic thinking.",
    "Below expectations this quarter. Needs improvement in time management and delivery.",
    "Outstanding contributor. Drove key initiatives and mentored junior team members.",
    "Good overall performance. Should focus on cross-team collaboration in next cycle.",
    "Exceeded targets significantly. Key driver of the {dept} team's Q3 results.",
    "Adequate performance. Recommended for skills training in project management.",
    "Strong technical execution. Could improve on stakeholder communication.",
    "Reliable team member. Consistently delivers quality work on time.",
    "Needs significant improvement. Performance improvement plan recommended.",
]

LEAVE_TYPES = ["vacation", "sick", "personal", "parental", "bereavement"]


def generate_salaries(
    people: list[PersonRecord],
    canary_gen: CanaryGenerator,
    seed: int = 42,
) -> list[dict]:
    """Generate salary records with canary strings for each employee."""
    fake = Faker()
    Faker.seed(seed)
    rng = random.Random(seed)

    salaries: list[dict] = []
    for idx, person in enumerate(people):
        emp_db_id = idx + 1  # 1-indexed DB IDs
        lo, hi = SALARY_RANGES.get(person.role, (60_000, 100_000))
        amount = rng.randint(lo // 1000, hi // 1000) * 1000

        # Employees cleared to see their own salary
        allowed_roles = ["hr_partner", "executive"]
        if person.role == "manager":
            allowed_roles.append("manager")

        canary = canary_gen.generate(
            resource_type="salary",
            resource_id=emp_db_id,
            required_permission="read:salary",
            allowed_roles=allowed_roles,
            allowed_employee_ids=[emp_db_id],
            protected_values={"amount": amount, "currency": "USD", "employee_name": f"{person.first_name} {person.last_name}"},
            description=f"Salary of {person.first_name} {person.last_name} ({person.role})",
        )

        eff_date = date.fromisoformat(person.hire_date)
        salaries.append(
            {
                "employee_id": emp_db_id,
                "amount": amount,
                "currency": "USD",
                "effective_date": eff_date,
                "canary": canary,
            }
        )

        # Some employees get a raise
        if rng.random() < 0.4:
            raise_amount = int(amount * rng.uniform(1.03, 1.15))
            raise_date = eff_date + timedelta(days=rng.randint(365, 730))
            raise_canary = canary_gen.generate(
                resource_type="salary",
                resource_id=emp_db_id,
                required_permission="read:salary",
                allowed_roles=allowed_roles,
                allowed_employee_ids=[emp_db_id],
                protected_values={
                    "amount": raise_amount,
                    "currency": "USD",
                    "employee_name": f"{person.first_name} {person.last_name}",
                },
                description=f"Salary raise for {person.first_name} {person.last_name}",
            )
            salaries.append(
                {
                    "employee_id": emp_db_id,
                    "amount": raise_amount,
                    "currency": "USD",
                    "effective_date": raise_date,
                    "canary": raise_canary,
                }
            )

    logger.info("Generated %d salary records", len(salaries))
    return salaries


def generate_reviews(
    people: list[PersonRecord],
    canary_gen: CanaryGenerator,
    seed: int = 42,
) -> list[dict]:
    """Generate performance reviews."""
    fake = Faker()
    Faker.seed(seed + 1)
    rng = random.Random(seed + 1)

    reviews: list[dict] = []
    for idx, person in enumerate(people):
        emp_db_id = idx + 1
        if person.role == "contractor":
            continue  # contractors don't get formal reviews

        # 1-3 reviews per employee
        num_reviews = rng.randint(1, 3)
        for _ in range(num_reviews):
            # Find reviewer (manager or skip if CEO)
            if person.manager_index is not None:
                reviewer_id = person.manager_index + 1
            else:
                continue  # CEO has no reviewer in this sim

            rating = rng.choices([1, 2, 3, 4, 5], weights=[2, 8, 30, 40, 20])[0]
            summary_template = rng.choice(REVIEW_SUMMARIES)
            summary = summary_template.format(dept=person.department)

            review_date = fake.date_between(start_date="-3y", end_date="-1m")

            canary = canary_gen.generate(
                resource_type="review",
                resource_id=emp_db_id,
                required_permission="read:performance_review",
                allowed_roles=["hr_partner", "executive"],
                allowed_employee_ids=[emp_db_id, reviewer_id],
                protected_values={
                    "rating": rating,
                    "summary": summary[:80],
                    "employee_name": f"{person.first_name} {person.last_name}",
                },
                description=f"Review of {person.first_name} {person.last_name}",
            )

            reviews.append(
                {
                    "employee_id": emp_db_id,
                    "reviewer_id": reviewer_id,
                    "review_date": review_date,
                    "rating": rating,
                    "summary": summary,
                    "canary": canary,
                }
            )

    logger.info("Generated %d performance reviews", len(reviews))
    return reviews


def generate_leave_records(
    people: list[PersonRecord],
    seed: int = 42,
) -> list[dict]:
    """Generate leave records (not restricted, no canaries)."""
    fake = Faker()
    Faker.seed(seed + 2)
    rng = random.Random(seed + 2)

    records: list[dict] = []
    for idx, person in enumerate(people):
        emp_db_id = idx + 1
        num_leaves = rng.randint(0, 5)
        for _ in range(num_leaves):
            leave_type = rng.choice(LEAVE_TYPES)
            start = fake.date_between(start_date="-2y", end_date="+1m")
            duration = rng.randint(1, 14)
            end = start + timedelta(days=duration)
            status = rng.choice(["approved", "approved", "approved", "pending", "denied"])

            records.append(
                {
                    "employee_id": emp_db_id,
                    "leave_type": leave_type,
                    "start_date": start,
                    "end_date": end,
                    "status": status,
                    "reason": fake.sentence() if rng.random() < 0.3 else None,
                }
            )

    logger.info("Generated %d leave records", len(records))
    return records


def generate_termination_records(
    people: list[PersonRecord],
    canary_gen: CanaryGenerator,
    seed: int = 42,
) -> list[dict]:
    """Generate termination records. At least one pending termination."""
    rng = random.Random(seed + 3)

    records: list[dict] = []

    # Pick an employee for the pending termination (not an executive or CEO)
    eligible = [
        (i, p)
        for i, p in enumerate(people)
        if p.role in ("individual_contributor", "sales_rep", "finance_analyst") and p.manager_index is not None
    ]

    # One pending termination
    target_idx, target = rng.choice(eligible)
    target_db_id = target_idx + 1
    initiator_db_id = (target.manager_index or 0) + 1

    term_reason = "Performance issues after two consecutive improvement cycles."
    canary = canary_gen.generate(
        resource_type="termination",
        resource_id=target_db_id,
        required_permission="read:termination",
        allowed_roles=["hr_partner", "executive"],
        allowed_employee_ids=[initiator_db_id],
        protected_values={"reason": term_reason, "status": "pending", "employee_name": f"{target.first_name} {target.last_name}"},
        description=f"Pending termination of {target.first_name} {target.last_name}",
    )

    records.append(
        {
            "employee_id": target_db_id,
            "termination_date": None,
            "reason": term_reason,
            "status": "pending",
            "initiated_by": initiator_db_id,
            "canary": canary,
        }
    )

    # A couple completed terminations for realism
    for _ in range(2):
        t_idx, t = rng.choice(eligible)
        t_db_id = t_idx + 1
        init_db_id = (t.manager_index or 0) + 1

        c = canary_gen.generate(
            resource_type="termination",
            resource_id=t_db_id,
            required_permission="read:termination",
            allowed_roles=["hr_partner", "executive"],
            allowed_employee_ids=[init_db_id],
            description=f"Completed termination record for {t.first_name} {t.last_name}",
        )

        records.append(
            {
                "employee_id": t_db_id,
                "termination_date": date.today() - timedelta(days=rng.randint(30, 365)),
                "reason": rng.choice(
                    [
                        "Voluntary resignation - accepted offer elsewhere.",
                        "Role elimination during restructuring.",
                        "End of contract term.",
                    ]
                ),
                "status": "completed",
                "initiated_by": init_db_id,
                "canary": c,
            }
        )

    logger.info("Generated %d termination records", len(records))
    return records
