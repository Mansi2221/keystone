"""Main seed script: builds the entire Meridian Freight company from scratch.

Usage: python -m company.seed
"""

import logging
from datetime import datetime

from company.canary import CanaryGenerator
from company.config import settings
from company.database import SessionLocal, reset_db
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
from company.models import (
    CanaryRecord,
    ChannelMember,
    ChatChannel,
    ChatMessage,
    Customer,
    Deal,
    Department,
    Document,
    DocumentChunk,
    Employee,
    LeaveRecord,
    PerformanceReview,
    Salary,
    TerminationRecord,
    Ticket,
    TicketComment,
)
from company.org_chart import DEPARTMENTS, generate_org_chart

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def seed_all() -> None:
    """Run the full seed process."""
    seed = settings.seed_random_seed
    canary_gen = CanaryGenerator(seed=seed)

    logger.info("=== Starting Meridian Freight seed (seed=%d) ===", seed)

    # Step 0: Reset database
    logger.info("Resetting database...")
    reset_db()

    session = SessionLocal()
    try:
        # Step 1: Departments
        logger.info("Creating departments...")
        dept_map: dict[str, int] = {}
        for dept_name in DEPARTMENTS:
            dept = Department(name=dept_name, description=f"{dept_name} department at Meridian Freight")
            session.add(dept)
            session.flush()
            dept_map[dept_name] = dept.id
        session.commit()
        logger.info("Created %d departments", len(dept_map))

        # Step 2: Org chart / Employees
        logger.info("Generating org chart...")
        people = generate_org_chart(seed=seed)

        logger.info("Inserting %d employees...", len(people))
        employee_db_ids: list[int] = []
        for person in people:
            emp = Employee(
                employee_id=f"MF-{len(employee_db_ids) + 1:04d}",
                first_name=person.first_name,
                last_name=person.last_name,
                email=person.email,
                role=person.role,
                title=person.title,
                department_id=dept_map[person.department],
                manager_id=employee_db_ids[person.manager_index] if person.manager_index is not None else None,
                hire_date=datetime.fromisoformat(person.hire_date).date(),
                is_active=person.is_active,
                groups=person.groups,
            )
            session.add(emp)
            session.flush()
            employee_db_ids.append(emp.id)
        session.commit()
        logger.info("Inserted %d employees", len(employee_db_ids))

        # Step 3: Salaries
        logger.info("Generating salaries...")
        salary_data = generate_salaries(people, canary_gen, seed=seed)
        for s in salary_data:
            session.add(Salary(**s))
        session.commit()
        logger.info("Inserted %d salary records", len(salary_data))

        # Step 4: Performance reviews
        logger.info("Generating performance reviews...")
        review_data = generate_reviews(people, canary_gen, seed=seed)
        for r in review_data:
            session.add(PerformanceReview(**r))
        session.commit()
        logger.info("Inserted %d reviews", len(review_data))

        # Step 5: Leave records
        logger.info("Generating leave records...")
        leave_data = generate_leave_records(people, seed=seed)
        for l in leave_data:
            session.add(LeaveRecord(**l))
        session.commit()
        logger.info("Inserted %d leave records", len(leave_data))

        # Step 6: Termination records
        logger.info("Generating termination records...")
        term_data = generate_termination_records(people, canary_gen, seed=seed)
        for t in term_data:
            session.add(TerminationRecord(**t))
        session.commit()
        logger.info("Inserted %d termination records", len(term_data))

        # Step 7: Tickets
        logger.info("Generating tickets...")
        ticket_data, comment_data = generate_tickets(people, canary_gen, seed=seed)
        for t in ticket_data:
            session.add(Ticket(**t))
        session.flush()
        for c in comment_data:
            db_id = c.pop("ticket_db_id")
            session.add(TicketComment(ticket_id=db_id, **c))
        session.commit()
        logger.info("Inserted %d tickets with %d comments", len(ticket_data), len(comment_data))

        # Step 8: Documents
        logger.info("Generating documents...")
        doc_data = generate_documents(people, canary_gen, seed=seed)
        for d in doc_data:
            doc = Document(**d)
            session.add(doc)
            session.flush()
            # Create a single chunk per document (embedding generated later)
            chunk = DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                content=d["content"][:2000],  # truncate for chunk
                access_groups=d["access_groups"],
            )
            session.add(chunk)
        session.commit()
        logger.info("Inserted %d documents", len(doc_data))

        # Step 9: Chat
        logger.info("Generating chat data...")
        channel_data, member_data, message_data = generate_chat(people, canary_gen, seed=seed)
        for ch in channel_data:
            session.add(ChatChannel(**ch))
        session.flush()
        for m in member_data:
            session.add(ChannelMember(**m))
        session.flush()
        for msg in message_data:
            session.add(ChatMessage(**msg))
        session.commit()
        logger.info(
            "Inserted %d channels, %d memberships, %d messages",
            len(channel_data),
            len(member_data),
            len(message_data),
        )

        # Step 10: CRM
        logger.info("Generating CRM data...")
        customer_data, deal_data = generate_crm(people, canary_gen, seed=seed)
        for c in customer_data:
            session.add(Customer(**c))
        session.flush()
        for d in deal_data:
            session.add(Deal(**d))
        session.commit()
        logger.info("Inserted %d customers and %d deals", len(customer_data), len(deal_data))

        # Step 11: Canary registry
        logger.info("Registering %d canaries...", canary_gen.count)
        for entry in canary_gen.entries:
            session.add(
                CanaryRecord(
                    canary=entry.canary,
                    resource_type=entry.resource_type,
                    resource_id=entry.resource_id,
                    required_permission=entry.required_permission,
                    allowed_roles=entry.allowed_roles,
                    allowed_employee_ids=entry.allowed_employee_ids,
                    protected_values=entry.protected_values,
                    description=entry.description,
                )
            )
        session.commit()
        logger.info("Registered %d canaries", canary_gen.count)

        # Summary
        logger.info("=== Seed complete ===")
        logger.info("  Departments:   %d", len(dept_map))
        logger.info("  Employees:     %d", len(people))
        logger.info("  Salaries:      %d", len(salary_data))
        logger.info("  Reviews:       %d", len(review_data))
        logger.info("  Leave records: %d", len(leave_data))
        logger.info("  Terminations:  %d", len(term_data))
        logger.info("  Tickets:       %d", len(ticket_data))
        logger.info("  Comments:      %d", len(comment_data))
        logger.info("  Documents:     %d", len(doc_data))
        logger.info("  Channels:      %d", len(channel_data))
        logger.info("  Messages:      %d", len(message_data))
        logger.info("  Customers:     %d", len(customer_data))
        logger.info("  Deals:         %d", len(deal_data))
        logger.info("  Canaries:      %d", canary_gen.count)

    except Exception:
        session.rollback()
        logger.exception("Seed failed!")
        raise
    finally:
        session.close()


def main() -> None:
    seed_all()

    # Dispose the SQLAlchemy engine pool to release all connections
    # before applying RLS (ALTER TABLE needs exclusive access).
    from company.database import engine

    engine.dispose()

    # Apply RLS policies after seeding
    from company.rls import apply_rls_policies

    logger.info("Applying RLS policies...")
    apply_rls_policies()
    logger.info("RLS policies applied.")

    # Grant keystone_app role access to all tables (RLS still applies)
    from company.database import execute_raw

    logger.info("Granting keystone_app permissions...")
    execute_raw("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO keystone_app")
    execute_raw("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO keystone_app")
    logger.info("keystone_app permissions granted.")


if __name__ == "__main__":
    main()
