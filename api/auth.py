"""JWT authentication and identity resolution.

- Seeded demo users for each role with a dev login endpoint
- Resolves role and groups from the HR system
- Attaches the Principal to every request unchanged
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select

from company.config import settings
from company.database import SessionLocal
from company.models import Department, Employee
from company.principal import Principal

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Demo users — lazily populated from DB on first access
DEMO_USERS: dict[str, dict[str, Any]] = {}


def get_demo_users() -> dict[str, dict[str, Any]]:
    """Return DEMO_USERS, building from DB on first call."""
    if not DEMO_USERS:
        DEMO_USERS.update(_build_demo_users())
    return DEMO_USERS


def _build_demo_users() -> dict[str, dict[str, Any]]:
    """Resolve demo users from the database so IDs always match seed data.

    Falls back to hardcoded IDs only if the DB is unavailable.
    """
    role_specs = [
        ("ceo", "executive", "CEO", None),
        ("vp_sales", "executive", "VP of Sales", "Sales"),
        ("vp_ops", "executive", "VP of Operations", "Operations"),
        ("cfo", "executive", "CFO", "Finance"),
        ("vp_people", "executive", "VP of People", "HR"),
        ("cto", "executive", "CTO", "Engineering"),
        ("sales_manager", "manager", None, "Sales"),
        ("ops_manager", "manager", None, "Operations"),
        ("hr_partner", "hr_partner", None, None),
        ("finance_analyst", "finance_analyst", None, None),
        ("sales_rep", "sales_rep", None, "Sales"),
        ("engineer", "individual_contributor", None, "Engineering"),
        ("contractor", "contractor", None, "Engineering"),
    ]

    try:
        session = SessionLocal()
        result: dict[str, dict[str, Any]] = {}
        for key, role, title_hint, dept_hint in role_specs:
            stmt = select(Employee).where(Employee.role == role)
            if dept_hint:
                stmt = stmt.join(Department, Employee.department_id == Department.id).where(Department.name == dept_hint)
            if title_hint:
                stmt = stmt.where(Employee.title == title_hint)
            stmt = stmt.order_by(Employee.id).limit(1)
            emp = session.execute(stmt).scalar_one_or_none()
            if emp:
                dept = session.execute(select(Department).where(Department.id == emp.department_id)).scalar_one_or_none()
                result[key] = {
                    "employee_id": emp.id,
                    "role": emp.role,
                    "description": emp.title,
                    "name": f"{emp.first_name} {emp.last_name}",
                    "department": dept.name if dept else "Unknown",
                }
            else:
                logger.warning("Demo user %s not found in DB (role=%s, dept=%s)", key, role, dept_hint)
        session.close()
        return result
    except Exception:
        logger.warning("Could not resolve demo users from DB, using hardcoded fallback")
        return {
            "ceo": {"employee_id": 1, "role": "executive", "description": "CEO"},
            "vp_sales": {"employee_id": 2, "role": "executive", "description": "VP of Sales"},
            "vp_ops": {"employee_id": 3, "role": "executive", "description": "VP of Operations"},
            "cfo": {"employee_id": 4, "role": "executive", "description": "CFO"},
            "vp_people": {"employee_id": 5, "role": "executive", "description": "VP of People"},
            "cto": {"employee_id": 6, "role": "executive", "description": "CTO"},
            "sales_manager": {"employee_id": 7, "role": "manager", "description": "Sales Manager"},
            "ops_manager": {"employee_id": 28, "role": "manager", "description": "Operations Manager"},
            "hr_partner": {"employee_id": 80, "role": "hr_partner", "description": "HR Business Partner"},
            "finance_analyst": {"employee_id": 64, "role": "finance_analyst", "description": "Financial Analyst"},
            "sales_rep": {"employee_id": 9, "role": "sales_rep", "description": "Account Executive"},
            "engineer": {"employee_id": 93, "role": "individual_contributor", "description": "Software Engineer"},
            "contractor": {"employee_id": 116, "role": "contractor", "description": "Contract Developer"},
        }


def create_access_token(employee_db_id: int, extra_claims: dict | None = None) -> str:
    """Create a JWT token for the given employee."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {
        "sub": str(employee_db_id),
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


def resolve_principal(employee_db_id: int) -> Principal:
    """Resolve a full Principal from the HR system by employee DB ID.

    This is the single source of truth for identity — the gateway calls this
    on every request and passes the result unchanged to all tool calls.
    """
    session = SessionLocal()
    try:
        emp = session.execute(select(Employee).where(Employee.id == employee_db_id)).scalar_one_or_none()

        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee {employee_db_id} not found",
            )

        dept = session.execute(select(Department).where(Department.id == emp.department_id)).scalar_one_or_none()

        # Compute direct and indirect reports
        report_ids = _get_all_report_ids(session, emp.id)

        return Principal(
            user_id=emp.id,
            employee_id=emp.employee_id,
            role=emp.role,
            department=dept.name if dept else "Unknown",
            groups=emp.groups or [],
            manager_id=emp.manager_id,
            report_ids=report_ids,
        )
    finally:
        session.close()


def _get_all_report_ids(session: Any, manager_id: int) -> list[int]:
    """Recursively get all direct and indirect report IDs."""
    direct = session.execute(select(Employee.id).where(Employee.manager_id == manager_id)).scalars().all()

    all_reports = list(direct)
    for rid in direct:
        all_reports.extend(_get_all_report_ids(session, rid))
    return all_reports


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Principal:
    """FastAPI dependency that extracts and validates the JWT, then resolves the Principal."""
    payload = decode_token(credentials.credentials)
    employee_db_id = int(payload["sub"])
    return resolve_principal(employee_db_id)
