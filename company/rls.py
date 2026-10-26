"""Row-Level Security setup and session context management.

Every database connection sets app.user_id, app.role, and app.groups
via SET LOCAL so that RLS policies can read them. The application DB role
(keystone_app) cannot bypass RLS.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import text
from sqlalchemy.orm import Session

from company.database import engine
from company.principal import Principal

logger = logging.getLogger(__name__)

# SQL to create RLS policies. Run once after table creation.
RLS_SETUP_SQL = """
-- Enable RLS on all user-scoped tables
ALTER TABLE salaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE termination_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticket_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE leave_records ENABLE ROW LEVEL SECURITY;

-- Force RLS for table owner too (important for the keystone superuser during dev)
ALTER TABLE salaries FORCE ROW LEVEL SECURITY;
ALTER TABLE performance_reviews FORCE ROW LEVEL SECURITY;
ALTER TABLE termination_records FORCE ROW LEVEL SECURITY;
ALTER TABLE tickets FORCE ROW LEVEL SECURITY;
ALTER TABLE ticket_comments FORCE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_channels FORCE ROW LEVEL SECURITY;
ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE deals FORCE ROW LEVEL SECURITY;
ALTER TABLE leave_records FORCE ROW LEVEL SECURITY;

-- ===== SALARY POLICIES =====
-- Own salary: employee can see their own (not contractors)
CREATE POLICY salary_own ON salaries FOR SELECT
    USING (
        employee_id = current_setting('app.user_id', true)::int
        AND current_setting('app.role', true) != 'contractor'
    );

-- Manager: can see direct/indirect reports' salaries
CREATE POLICY salary_manager ON salaries FOR SELECT
    USING (
        current_setting('app.role', true) IN ('manager')
        AND employee_id = ANY(
            string_to_array(current_setting('app.report_ids', true), ',')::int[]
        )
    );

-- HR partners and executives: see all salaries
CREATE POLICY salary_hr_exec ON salaries FOR SELECT
    USING (
        current_setting('app.role', true) IN ('hr_partner', 'executive')
    );

-- ===== PERFORMANCE REVIEW POLICIES =====
-- Own reviews: employee sees their own (not contractors)
CREATE POLICY review_own ON performance_reviews FOR SELECT
    USING (
        (employee_id = current_setting('app.user_id', true)::int
         OR reviewer_id = current_setting('app.user_id', true)::int)
        AND current_setting('app.role', true) != 'contractor'
    );

-- HR partners and executives: see all reviews
CREATE POLICY review_hr_exec ON performance_reviews FOR SELECT
    USING (
        current_setting('app.role', true) IN ('hr_partner', 'executive')
    );

-- ===== TERMINATION POLICIES =====
-- Only HR partners and executives
CREATE POLICY termination_hr_exec ON termination_records FOR SELECT
    USING (
        current_setting('app.role', true) IN ('hr_partner', 'executive')
    );

-- Initiator can see their own initiated terminations
CREATE POLICY termination_initiator ON termination_records FOR SELECT
    USING (
        initiated_by = current_setting('app.user_id', true)::int
    );

-- ===== TICKET POLICIES =====
-- Own tickets and tickets assigned to user
CREATE POLICY ticket_own ON tickets FOR SELECT
    USING (
        owner_id = current_setting('app.user_id', true)::int
        OR assignee_id = current_setting('app.user_id', true)::int
    );

-- Team tickets for managers and ICs (same department)
CREATE POLICY ticket_team ON tickets FOR SELECT
    USING (
        current_setting('app.role', true) IN ('individual_contributor', 'manager', 'sales_rep', 'finance_analyst')
        AND team = ANY(
            string_to_array(current_setting('app.groups', true), ',')
        )
    );

-- HR partners see HR complaint tickets
CREATE POLICY ticket_hr ON tickets FOR SELECT
    USING (
        current_setting('app.role', true) = 'hr_partner'
        AND category IN ('hr_complaint', 'it', 'ops')
    );

-- Executives see all tickets
CREATE POLICY ticket_exec ON tickets FOR SELECT
    USING (
        current_setting('app.role', true) = 'executive'
    );

-- Ticket comments follow ticket visibility (simplified: visible if ticket is visible)
CREATE POLICY comment_select ON ticket_comments FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM tickets t WHERE t.id = ticket_comments.ticket_id
        )
    );

-- ===== DOCUMENT POLICIES =====
-- Documents visible if user's groups overlap with access_groups
CREATE POLICY doc_access ON documents FOR SELECT
    USING (
        access_groups && string_to_array(current_setting('app.groups', true), ',')::text[]
        OR current_setting('app.role', true) = 'executive'
        OR owner_id = current_setting('app.user_id', true)::int
    );

-- Document chunks follow document access
CREATE POLICY chunk_access ON document_chunks FOR SELECT
    USING (
        access_groups && string_to_array(current_setting('app.groups', true), ',')::text[]
        OR current_setting('app.role', true) = 'executive'
    );

-- ===== CHAT POLICIES =====
-- Channels: public channels visible to all, private/DM visible to members only
CREATE POLICY channel_public ON chat_channels FOR SELECT
    USING (
        NOT is_private
    );

CREATE POLICY channel_member ON chat_channels FOR SELECT
    USING (
        is_private AND EXISTS (
            SELECT 1 FROM channel_members cm
            WHERE cm.channel_id = chat_channels.id
            AND cm.employee_id = current_setting('app.user_id', true)::int
        )
    );

-- Messages: visible if channel is visible (enforced via channel RLS)
CREATE POLICY message_access ON chat_messages FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM chat_channels ch
            WHERE ch.id = chat_messages.channel_id
        )
    );

-- ===== DEAL POLICIES =====
-- Owner sees their own deals
CREATE POLICY deal_owner ON deals FOR SELECT
    USING (
        owner_id = current_setting('app.user_id', true)::int
    );

-- Sales leadership (managers in Sales) see all deals
CREATE POLICY deal_sales_lead ON deals FOR SELECT
    USING (
        current_setting('app.role', true) IN ('manager', 'executive')
        AND 'sales' = ANY(string_to_array(current_setting('app.groups', true), ','))
    );

-- Executives see all deals
CREATE POLICY deal_exec ON deals FOR SELECT
    USING (
        current_setting('app.role', true) = 'executive'
    );

-- ===== LEAVE RECORD POLICIES =====
-- Own leave records
CREATE POLICY leave_own ON leave_records FOR SELECT
    USING (
        employee_id = current_setting('app.user_id', true)::int
    );

-- Manager sees their reports' leave
CREATE POLICY leave_manager ON leave_records FOR SELECT
    USING (
        current_setting('app.role', true) IN ('manager')
        AND employee_id = ANY(
            string_to_array(current_setting('app.report_ids', true), ',')::int[]
        )
    );

-- HR and executives see all
CREATE POLICY leave_hr_exec ON leave_records FOR SELECT
    USING (
        current_setting('app.role', true) IN ('hr_partner', 'executive')
    );
"""


def apply_rls_policies() -> None:
    """Apply all RLS policies to the database.

    Should be run after tables are created and seeded.
    """
    with engine.connect() as conn:
        # Drop existing policies first to allow re-running
        conn.execute(text("""
            DO $$
            DECLARE
                pol RECORD;
            BEGIN
                FOR pol IN
                    SELECT policyname, tablename FROM pg_policies
                    WHERE schemaname = 'public'
                LOOP
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol.policyname, pol.tablename);
                END LOOP;
            END $$;
        """))

        # Disable RLS first (to allow clean re-enable)
        tables_with_rls = [
            "salaries", "performance_reviews", "termination_records",
            "tickets", "ticket_comments", "documents", "document_chunks",
            "chat_channels", "chat_messages", "deals", "leave_records",
        ]
        for table in tables_with_rls:
            conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

        # Now apply all policies
        for statement in RLS_SETUP_SQL.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                conn.execute(text(stmt))

        conn.commit()
    logger.info("RLS policies applied successfully")


@contextmanager
def rls_session(principal: Principal) -> Generator[Session, None, None]:
    """Create a database session with RLS context set for the given principal.

    Sets app.user_id, app.role, app.groups, and app.report_ids via SET LOCAL
    so that all queries within this session are filtered by RLS policies.
    """
    with Session(engine) as session:
        with session.begin():
            # SET LOCAL only lasts for the current transaction
            session.execute(
                text("SET LOCAL app.user_id = :uid"),
                {"uid": str(principal.user_id)},
            )
            session.execute(
                text("SET LOCAL app.role = :role"),
                {"role": principal.role},
            )
            session.execute(
                text("SET LOCAL app.groups = :groups"),
                {"groups": ",".join(principal.groups)},
            )
            session.execute(
                text("SET LOCAL app.report_ids = :rids"),
                {"rids": ",".join(str(r) for r in principal.report_ids) if principal.report_ids else "0"},
            )
            yield session
