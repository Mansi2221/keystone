"""Database engine and session management."""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from company.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.sync_database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


def init_db() -> None:
    """Initialize the database schema by running the init SQL."""
    from company.models import Base

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")


def reset_db() -> None:
    """Drop and recreate all tables. Used during seeding."""
    from company.models import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset complete.")


def execute_raw(sql: str) -> None:
    """Execute raw SQL against the database."""
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
