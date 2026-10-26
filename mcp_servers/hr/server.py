"""HR MCP Server — exposes tools for querying HR data.

Read tools: search_employees, get_employee, get_salary, get_reviews, get_leave
Write tools: none (HR is read-only for the agent)

All queries go through RLS-protected sessions.
"""

import logging
from typing import Any

from sqlalchemy import select, func

from company.models import (
    Department,
    Employee,
    LeaveRecord,
    PerformanceReview,
    Salary,
    TerminationRecord,
)
from company.principal import Principal
from company.rls import rls_session
from mcp_servers.base import access_denied, tool_result

logger = logging.getLogger(__name__)


def search_employees(
    principal: Principal,
    query: str = "",
    department: str = "",
    role: str = "",
    limit: int = 20,
) -> dict:
    """Search employees by name, department, or role.

    Employee directory is visible to all (basic info only).
    """
    with rls_session(principal) as session:
        # Employee basic info is not RLS-protected; it's a directory
        stmt = select(Employee).join(Department)
        if query:
            stmt = stmt.where(
                (Employee.first_name.ilike(f"%{query}%"))
                | (Employee.last_name.ilike(f"%{query}%"))
                | (Employee.email.ilike(f"%{query}%"))
            )
        if department:
            stmt = stmt.where(Department.name.ilike(f"%{department}%"))
        if role:
            stmt = stmt.where(Employee.role == role)
        stmt = stmt.limit(limit)

        results = session.execute(stmt).scalars().all()
        return tool_result([
            {
                "id": e.id,
                "employee_id": e.employee_id,
                "name": f"{e.first_name} {e.last_name}",
                "email": e.email,
                "role": e.role,
                "title": e.title,
                "department": e.department.name,
                "is_active": e.is_active,
            }
            for e in results
        ])


def get_employee(principal: Principal, employee_id: int) -> dict:
    """Get detailed employee information."""
    with rls_session(principal) as session:
        emp = session.get(Employee, employee_id)
        if not emp:
            return tool_result(None, error=f"Employee {employee_id} not found")

        data: dict[str, Any] = {
            "id": emp.id,
            "employee_id": emp.employee_id,
            "name": f"{emp.first_name} {emp.last_name}",
            "email": emp.email,
            "role": emp.role,
            "title": emp.title,
            "department": emp.department.name,
            "hire_date": emp.hire_date.isoformat(),
            "is_active": emp.is_active,
            "manager_id": emp.manager_id,
        }
        return tool_result(data)


def get_salary(principal: Principal, employee_id: int) -> dict:
    """Get salary records for an employee. Protected by RLS."""
    with rls_session(principal) as session:
        stmt = (
            select(Salary)
            .where(Salary.employee_id == employee_id)
            .order_by(Salary.effective_date.desc())
        )
        results = session.execute(stmt).scalars().all()

        if not results:
            # Could be no access (RLS filtered) or no records
            return access_denied(
                "salary records",
                "You can only view your own salary, your reports' (if manager), or all (if HR/executive).",
            )

        return tool_result([
            {
                "employee_id": s.employee_id,
                "amount": s.amount,
                "currency": s.currency,
                "effective_date": s.effective_date.isoformat(),
            }
            for s in results
        ])


def get_reviews(principal: Principal, employee_id: int) -> dict:
    """Get performance reviews for an employee. Protected by RLS."""
    with rls_session(principal) as session:
        stmt = (
            select(PerformanceReview)
            .where(PerformanceReview.employee_id == employee_id)
            .order_by(PerformanceReview.review_date.desc())
        )
        results = session.execute(stmt).scalars().all()

        if not results:
            return access_denied(
                "performance reviews",
                "You can only view your own reviews or all (if HR/executive).",
            )

        return tool_result([
            {
                "employee_id": r.employee_id,
                "reviewer_id": r.reviewer_id,
                "review_date": r.review_date.isoformat(),
                "rating": r.rating,
                "summary": r.summary,
            }
            for r in results
        ])


def get_leave_records(principal: Principal, employee_id: int) -> dict:
    """Get leave records for an employee. Protected by RLS."""
    with rls_session(principal) as session:
        stmt = (
            select(LeaveRecord)
            .where(LeaveRecord.employee_id == employee_id)
            .order_by(LeaveRecord.start_date.desc())
        )
        results = session.execute(stmt).scalars().all()

        if not results:
            return access_denied("leave records")

        return tool_result([
            {
                "employee_id": l.employee_id,
                "leave_type": l.leave_type,
                "start_date": l.start_date.isoformat(),
                "end_date": l.end_date.isoformat(),
                "status": l.status,
                "reason": l.reason,
            }
            for l in results
        ])


def get_org_chart(principal: Principal, root_employee_id: int | None = None) -> dict:
    """Get the org chart as a tree structure. Visible to all."""
    with rls_session(principal) as session:
        stmt = select(Employee).join(Department)
        if root_employee_id:
            # Get subtree under this manager
            all_emps = session.execute(stmt).scalars().all()
            emp_map = {e.id: e for e in all_emps}

            def build_tree(eid: int) -> dict:
                e = emp_map[eid]
                reports = [
                    build_tree(r.id) for r in all_emps if r.manager_id == eid
                ]
                return {
                    "id": e.id,
                    "name": f"{e.first_name} {e.last_name}",
                    "title": e.title,
                    "department": e.department.name,
                    "reports": reports,
                }

            if root_employee_id not in emp_map:
                return tool_result(None, error="Employee not found")
            return tool_result(build_tree(root_employee_id))

        # Full org
        all_emps = session.execute(stmt).scalars().all()
        return tool_result([
            {
                "id": e.id,
                "name": f"{e.first_name} {e.last_name}",
                "title": e.title,
                "department": e.department.name,
                "manager_id": e.manager_id,
            }
            for e in all_emps
        ])


# Tool registry for the MCP protocol
TOOLS = {
    "hr_search_employees": {
        "function": search_employees,
        "description": "Search the employee directory by name, department, or role",
        "parameters": {
            "query": {"type": "string", "description": "Name or email search term"},
            "department": {"type": "string", "description": "Filter by department name"},
            "role": {"type": "string", "description": "Filter by role"},
            "limit": {"type": "integer", "description": "Max results (default 20)"},
        },
    },
    "hr_get_employee": {
        "function": get_employee,
        "description": "Get detailed information about a specific employee",
        "parameters": {
            "employee_id": {"type": "integer", "description": "Employee database ID", "required": True},
        },
    },
    "hr_get_salary": {
        "function": get_salary,
        "description": "Get salary history for an employee (restricted by permissions)",
        "parameters": {
            "employee_id": {"type": "integer", "description": "Employee database ID", "required": True},
        },
    },
    "hr_get_reviews": {
        "function": get_reviews,
        "description": "Get performance reviews for an employee (restricted by permissions)",
        "parameters": {
            "employee_id": {"type": "integer", "description": "Employee database ID", "required": True},
        },
    },
    "hr_get_leave": {
        "function": get_leave_records,
        "description": "Get leave records for an employee",
        "parameters": {
            "employee_id": {"type": "integer", "description": "Employee database ID", "required": True},
        },
    },
    "hr_get_org_chart": {
        "function": get_org_chart,
        "description": "Get the organizational chart, optionally rooted at a specific employee",
        "parameters": {
            "root_employee_id": {"type": "integer", "description": "Root employee ID (optional)"},
        },
    },
}
