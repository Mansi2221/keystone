"""JWT authentication and identity resolution.

- Seeded demo users for each role with a dev login endpoint
- Resolves role and groups from the HR system
- Attaches the Principal to every request unchanged
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from company.config import settings
from company.database import SessionLocal
from company.models import Employee, Department
from company.principal import Principal
from sqlalchemy import select

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Demo users seeded for each role (populated at import time from DB, or hardcoded fallback)
DEMO_USERS: dict[str, dict[str, Any]] = {
    "ceo": {"employee_id": 1, "role": "executive", "description": "CEO"},
    "vp_sales": {"employee_id": 2, "role": "executive", "description": "VP of Sales"},
    "vp_ops": {"employee_id": 3, "role": "executive", "description": "VP of Operations"},
    "cfo": {"employee_id": 4, "role": "executive", "description": "CFO"},
    "vp_people": {"employee_id": 5, "role": "executive", "description": "VP of People"},
    "cto": {"employee_id": 6, "role": "executive", "description": "CTO"},
    "sales_manager": {"employee_id": 7, "role": "manager", "description": "Sales Manager"},
    "ops_manager": {"employee_id": 8, "role": "manager", "description": "Operations Manager"},
    "hr_partner": {"employee_id": 12, "role": "hr_partner", "description": "HR Business Partner"},
    "finance_analyst": {"employee_id": 15, "role": "finance_analyst", "description": "Financial Analyst"},
    "sales_rep": {"employee_id": 10, "role": "sales_rep", "description": "Account Executive"},
    "engineer": {"employee_id": 20, "role": "individual_contributor", "description": "Software Engineer"},
    "contractor": {"employee_id": 25, "role": "contractor", "description": "Contract Developer"},
}


def create_access_token(employee_db_id: int, extra_claims: dict | None = None) -> str:
    """Create a JWT token for the given employee."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {
        "sub": str(employee_db_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
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
        emp = session.execute(
            select(Employee).where(Employee.id == employee_db_id)
        ).scalar_one_or_none()

        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Employee {employee_db_id} not found",
            )

        dept = session.execute(
            select(Department).where(Department.id == emp.department_id)
        ).scalar_one_or_none()

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
    direct = session.execute(
        select(Employee.id).where(Employee.manager_id == manager_id)
    ).scalars().all()

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
