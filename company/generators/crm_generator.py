"""Generate CRM data: customers and deals with access controls."""

import logging
import random
from datetime import timedelta

from faker import Faker

from company.canary import CanaryGenerator
from company.org_chart import PersonRecord

logger = logging.getLogger(__name__)

DEAL_STAGES = [
    "prospecting",
    "qualification",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
]

INDUSTRIES = [
    "Manufacturing",
    "Retail",
    "Technology",
    "Healthcare",
    "Agriculture",
    "Automotive",
    "Food & Beverage",
    "Construction",
    "Energy",
    "Pharmaceuticals",
    "Consumer Goods",
    "E-commerce",
]

DEAL_TITLE_TEMPLATES = [
    "{company} - Annual Shipping Contract",
    "{company} - Warehouse Services",
    "{company} - Last Mile Delivery",
    "{company} - Cross-Border Logistics",
    "{company} - Cold Chain Solution",
    "{company} - Fleet Management",
    "{company} - Supply Chain Optimization",
    "{company} - Express Freight Service",
    "{company} - Bulk Transport Agreement",
    "{company} - Regional Distribution",
]


def generate_crm(
    people: list[PersonRecord],
    canary_gen: CanaryGenerator,
    num_customers: int = 80,
    num_deals: int = 150,
    seed: int = 42,
) -> tuple[list[dict], list[dict]]:
    """Generate customers and deals.

    Returns (customers, deals).
    """
    fake = Faker()
    Faker.seed(seed + 40)
    rng = random.Random(seed + 40)

    # Find sales reps and sales leadership
    sales_reps: list[int] = []
    sales_leaders: list[int] = []
    for idx, p in enumerate(people):
        db_id = idx + 1
        if p.department == "Sales":
            if p.role in ("sales_rep", "individual_contributor"):
                sales_reps.append(db_id)
            elif p.role in ("manager", "executive"):
                sales_leaders.append(db_id)

    # If no sales reps found, fall back
    if not sales_reps:
        sales_reps = list(range(1, min(10, len(people) + 1)))
    if not sales_leaders:
        sales_leaders = sales_reps[:2]

    # --- Customers ---
    customers: list[dict] = []
    for i in range(num_customers):
        customers.append(
            {
                "name": fake.company(),
                "industry": rng.choice(INDUSTRIES),
                "contact_email": fake.company_email(),
                "created_at": fake.date_time_between(start_date="-5y", end_date="-1m"),
            }
        )

    # --- Deals ---
    deals: list[dict] = []
    for i in range(num_deals):
        customer_db_id = rng.randint(1, num_customers)
        owner_id = rng.choice(sales_reps)
        customer_name = customers[customer_db_id - 1]["name"]

        title_template = rng.choice(DEAL_TITLE_TEMPLATES)
        title = title_template.format(company=customer_name)

        stage = rng.choices(
            DEAL_STAGES,
            weights=[15, 20, 25, 15, 15, 10],
        )[0]

        value = round(rng.uniform(10_000, 5_000_000), 2)
        created_at = fake.date_time_between(start_date="-2y", end_date="-1w")
        updated_at = created_at + timedelta(days=rng.randint(1, 180))

        deal_id = f"DEAL-{i + 1:04d}"

        # All deals are visible only to owner + sales leadership
        canary = canary_gen.generate(
            resource_type="deal",
            resource_id=i + 1,
            required_permission="read:deal",
            allowed_roles=["executive"],
            allowed_employee_ids=[owner_id] + sales_leaders,
            description=f"Deal {deal_id}: {title} (${value:,.0f})",
        )

        deals.append(
            {
                "deal_id": deal_id,
                "customer_id": customer_db_id,
                "owner_id": owner_id,
                "title": title,
                "value": value,
                "stage": stage,
                "created_at": created_at,
                "updated_at": updated_at,
                "canary": canary,
            }
        )

    logger.info("Generated %d customers and %d deals", len(customers), len(deals))
    return customers, deals
