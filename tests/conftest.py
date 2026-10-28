"""Shared test fixtures."""

import pytest


@pytest.fixture(scope="session")
def seed_data():
    """Generate all seed data in-memory for testing (no database required).

    This fixture runs the generators and returns the raw data for validation.
    """
    from company.canary import CanaryGenerator
    from company.generators.chat_generator import generate_chat
    from company.generators.crm_generator import generate_crm
    from company.generators.doc_generator import generate_documents
    from company.generators.hr_generator import (
        generate_leave_records,
        generate_reviews,
        generate_salaries,
        generate_termination_records,
    )
    from company.generators.ticket_generator import generate_tickets
    from company.org_chart import generate_org_chart

    seed = 42
    canary_gen = CanaryGenerator(seed=seed)
    people = generate_org_chart(seed=seed)
    salaries = generate_salaries(people, canary_gen, seed=seed)
    reviews = generate_reviews(people, canary_gen, seed=seed)
    leaves = generate_leave_records(people, seed=seed)
    terminations = generate_termination_records(people, canary_gen, seed=seed)
    tickets, comments = generate_tickets(people, canary_gen, seed=seed)
    documents = generate_documents(people, canary_gen, seed=seed)
    channels, members, messages = generate_chat(people, canary_gen, seed=seed)
    customers, deals = generate_crm(people, canary_gen, seed=seed)

    return {
        "people": people,
        "salaries": salaries,
        "reviews": reviews,
        "leaves": leaves,
        "terminations": terminations,
        "tickets": tickets,
        "comments": comments,
        "documents": documents,
        "channels": channels,
        "members": members,
        "messages": messages,
        "customers": customers,
        "deals": deals,
        "canary_gen": canary_gen,
    }
