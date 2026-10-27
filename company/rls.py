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
        access_groups && string_to_array(current_setting('app.groups', true), ',')::varchar[]
        OR current_setting('app.role', true) = 'executive'
        OR owner_id = current_setting('app.user_id', true)::int
    );

-- Document chunks follow document access
CREATE POLICY chunk_access ON document_chunks FOR SELECT
    USING (
        access_groups && string_to_array(current_setting('app.groups', true), ',')::varchar[]
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


RLS_TABLES = [
    "salaries", "performance_reviews", "termination_records",
    "tickets", "ticket_comments", "documents", "document_chunks",
    "chat_channels", "chat_messages", "deals", "leave_records",
]


def disable_all_rls() -> None:
    """Disable RLS on all tables. EVAL MODE ONLY.

    Raises RuntimeError if called outside eval_mode.
    """
    from company.config import settings
    if not settings.eval_mode:
        raise RuntimeError("Cannot disable RLS outside eval mode")

    import psycopg
    raw_url = settings.raw_database_url
    with psycopg.connect(raw_url, autocommit=True) as conn:
        cur = conn.cursor()
        # Drop all existing policies
        cur.execute("""
            DO $$
            DECLARE pol RECORD;
            BEGIN
                FOR pol IN
                    SELECT policyname, tablename FROM pg_policies
                    WHERE schemaname = 'public'
                LOOP
                    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol.policyname, pol.tablename);
                END LOOP;
            END $$;
        """)
        for table in RLS_TABLES:
            cur.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        cur.close()
    logger.warning("RLS DISABLED on all tables (eval ablation mode)")


def enable_all_rls() -> None:
    """Re-enable RLS on all tables by applying full policy set."""
    apply_rls_policies()
    logger.info("RLS RE-ENABLED on all tables")


def apply_rls_policies() -> None:
    """Apply all RLS policies to the database.

    Uses a direct psycopg connection with autocommit to execute the multi-statement
    RLS SQL block. SQLAlchemy's text() can't handle multi-statement SQL in psycopg3.
    """
    import psycopg
    from company.config import settings

    raw_url = settings.raw_database_url
    with psycopg.connect(raw_url, autocommit=True) as conn:
        cur = conn.cursor()

        # Drop existing policies first
        cur.execute("""
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
        """)

        # Disable RLS on all tables first
        tables_with_rls = [
            "salaries", "performance_reviews", "termination_records",
            "tickets", "ticket_comments", "documents", "document_chunks",
            "chat_channels", "chat_messages", "deals", "leave_records",
        ]
        for table in tables_with_rls:
            cur.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

        # Split RLS_SETUP_SQL into individual statements.
        # Track parenthesis depth so we don't split inside subqueries.
        stmts = _split_sql_statements(RLS_SETUP_SQL)
        for stmt in stmts:
            cur.execute(stmt)
        cur.close()

    logger.info("RLS policies applied successfully")


def _split_sql_statements(sql: str) -> list[str]:
    """Split multi-statement SQL into individual statements.

    Handles statements that contain subqueries with semicolons
    by tracking parenthesis depth.
    """
    stmts = []
    current: list[str] = []
    depth = 0
    for line in sql.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        depth += line.count("(") - line.count(")")
        if stripped.endswith(";") and depth <= 0:
            stmt = "\n".join(current).strip().rstrip(";").strip()
            if stmt:
                stmts.append(stmt)
            current = []
            depth = 0
    if current:
        stmt = "\n".join(current).strip().rstrip(";").strip()
        if stmt:
            stmts.append(stmt)
    return stmts


@contextmanager
def rls_session(principal: Principal) -> Generator[Session, None, None]:
    """Create a database session with RLS context set for the given principal.

    Sets app.user_id, app.role, app.groups, and app.report_ids via SET LOCAL
    so that all queries within this session are filtered by RLS policies.
    """
    with Session(engine) as session:
        with session.begin():
            # SET LOCAL only lasts for the current transaction.
            # psycopg3 doesn't support parameterized SET, so we use
            # quote_literal via format to safely inject values.
            uid = str(int(principal.user_id))  # Ensure it's a safe int
            role = principal.role.replace("'", "''")
            groups = ",".join(principal.groups).replace("'", "''")
            rids = (
                ",".join(str(int(r)) for r in principal.report_ids)
                if principal.report_ids else "0"
            )
            session.execute(text(f"SET LOCAL app.user_id = '{uid}'"))
            session.execute(text(f"SET LOCAL app.role = '{role}'"))
            session.execute(text(f"SET LOCAL app.groups = '{groups}'"))
            session.execute(text(f"SET LOCAL app.report_ids = '{rids}'"))
            yield session
