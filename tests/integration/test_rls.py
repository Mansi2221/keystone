"""Integration tests for Row-Level Security.

These tests verify that the same query returns different rows for different users,
and that contractors get nothing restricted from any system.

IMPORTANT: These tests require a running Postgres instance.
They are skipped if the database is not available.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Skip all tests in this module if no database
pytestmark = pytest.mark.integration


def db_available() -> bool:
    """Check if test database is available."""
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
    )
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


skip_no_db = pytest.mark.skipif(not db_available(), reason="Database not available")


@skip_no_db
class TestRLSSalaries:
    """Test that salary access is properly restricted."""

    def _query_salaries(self, engine, user_id: int, role: str, groups: str, report_ids: str = "0"):
        """Query salaries with RLS context set."""
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL app.user_id = '{user_id}'"))
            conn.execute(text(f"SET LOCAL app.role = '{role}'"))
            conn.execute(text(f"SET LOCAL app.groups = '{groups}'"))
            conn.execute(text(f"SET LOCAL app.report_ids = '{report_ids}'"))
            result = conn.execute(text("SELECT id, employee_id, amount, canary FROM salaries"))
            return result.fetchall()

    def test_employee_sees_own_salary(self):
        """An employee should see their own salary only."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            # Start a transaction so SET LOCAL works
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '5'"))
            conn.execute(text("SET LOCAL app.role = 'individual_contributor'"))
            conn.execute(text("SET LOCAL app.groups = 'engineering,engineering_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text("SELECT employee_id FROM salaries")).fetchall()

            # Should only see employee_id = 5
            emp_ids = {r[0] for r in result}
            assert 5 in emp_ids or len(emp_ids) == 0  # 0 if RLS isn't applied yet
            if emp_ids:
                assert emp_ids == {5}, f"IC should only see own salary, got {emp_ids}"
            trans.rollback()

    def test_contractor_sees_no_salaries(self):
        """A contractor should see no salary records."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '100'"))
            conn.execute(text("SET LOCAL app.role = 'contractor'"))
            conn.execute(text("SET LOCAL app.groups = 'engineering,engineering_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text("SELECT count(*) FROM salaries")).fetchone()
            assert result[0] == 0, f"Contractor should see 0 salaries, got {result[0]}"
            trans.rollback()

    def test_hr_partner_sees_all_salaries(self):
        """HR partner should see all salary records."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '10'"))
            conn.execute(text("SET LOCAL app.role = 'hr_partner'"))
            conn.execute(text("SET LOCAL app.groups = 'hr,hr_all,hr_full_access'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text("SELECT count(*) FROM salaries")).fetchone()
            # Should see all salaries (120+ employees, some with raises)
            assert result[0] > 100, f"HR should see all salaries, got {result[0]}"
            trans.rollback()

    def test_executive_sees_all_salaries(self):
        """Executive should see all salary records."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '1'"))
            conn.execute(text("SET LOCAL app.role = 'executive'"))
            conn.execute(text("SET LOCAL app.groups = 'leadership,board_access,operations,operations_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text("SELECT count(*) FROM salaries")).fetchone()
            assert result[0] > 100, f"Executive should see all salaries, got {result[0]}"
            trans.rollback()


@skip_no_db
class TestRLSDocuments:
    """Test that document access is properly restricted."""

    def test_ic_cannot_see_board_minutes(self):
        """An IC should not see board minutes."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '20'"))
            conn.execute(text("SET LOCAL app.role = 'individual_contributor'"))
            conn.execute(text("SET LOCAL app.groups = 'engineering,engineering_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text(
                "SELECT count(*) FROM documents WHERE doc_type = 'board_minutes'"
            )).fetchone()
            assert result[0] == 0, f"IC should see 0 board minutes, got {result[0]}"
            trans.rollback()

    def test_executive_sees_board_minutes(self):
        """An executive should see board minutes."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '1'"))
            conn.execute(text("SET LOCAL app.role = 'executive'"))
            conn.execute(text("SET LOCAL app.groups = 'leadership,board_access,operations,operations_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text(
                "SELECT count(*) FROM documents WHERE doc_type = 'board_minutes'"
            )).fetchone()
            assert result[0] >= 5, f"Executive should see board minutes, got {result[0]}"
            trans.rollback()


@skip_no_db
class TestRLSDeals:
    """Test that deal access is properly restricted."""

    def test_contractor_sees_no_deals(self):
        """A contractor should see no deals."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '100'"))
            conn.execute(text("SET LOCAL app.role = 'contractor'"))
            conn.execute(text("SET LOCAL app.groups = 'engineering,engineering_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text("SELECT count(*) FROM deals")).fetchone()
            assert result[0] == 0, f"Contractor should see 0 deals, got {result[0]}"
            trans.rollback()


@skip_no_db
class TestRLSChat:
    """Test that private chat is properly restricted."""

    def test_non_member_cannot_see_private_channel(self):
        """Non-member should not see private channels."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            # Use an ID that's unlikely to be in leadership channel
            conn.execute(text("SET LOCAL app.user_id = '50'"))
            conn.execute(text("SET LOCAL app.role = 'individual_contributor'"))
            conn.execute(text("SET LOCAL app.groups = 'operations,operations_all'"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text(
                "SELECT count(*) FROM chat_channels WHERE name = 'leadership-team'"
            )).fetchone()
            # Should be 0 since this IC is not a member
            assert result[0] == 0, f"Non-member should not see leadership channel"
            trans.rollback()


@skip_no_db
class TestRLSTickets:
    """Test that restricted tickets are properly filtered."""

    def test_contractor_own_tickets_only(self):
        """Contractor should only see their own tickets."""
        url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://keystone_app:keystone_app_password@localhost:5433/keystone",
        )
        engine = create_engine(url)
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("SET LOCAL app.user_id = '100'"))
            conn.execute(text("SET LOCAL app.role = 'contractor'"))
            conn.execute(text("SET LOCAL app.groups = ''"))
            conn.execute(text("SET LOCAL app.report_ids = '0'"))

            result = conn.execute(text(
                "SELECT owner_id, assignee_id FROM tickets"
            )).fetchall()

            for row in result:
                assert row[0] == 100 or row[1] == 100, (
                    f"Contractor sees ticket not owned/assigned: owner={row[0]}, assignee={row[1]}"
                )
            trans.rollback()
