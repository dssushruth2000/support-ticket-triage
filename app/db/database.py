"""SQLAlchemy engine and session management.

Uses the ``DATABASE_URL`` from settings. For SQLite we pass the extra
connect arg required for use across threads (FastAPI/uvicorn). Switching to
Postgres/Supabase needs no change here beyond the URL.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly.

    Also applies lightweight additive SQLite column migrations so existing local
    DBs pick up Phase 4 fields without a manual wipe.
    """
    from sqlalchemy import text

    from app.db import models  # noqa: F401  (ensure models are registered)
    from app.db.models import Base

    Base.metadata.create_all(bind=engine)

    if _is_sqlite:
        with engine.begin() as conn:
            existing = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(resolutions)")).fetchall()
            }
            for col, ddl in (
                ("model_tier", "ALTER TABLE resolutions ADD COLUMN model_tier VARCHAR(16)"),
                ("model_name", "ALTER TABLE resolutions ADD COLUMN model_name VARCHAR(64)"),
                ("route_reason", "ALTER TABLE resolutions ADD COLUMN route_reason TEXT"),
            ):
                if col not in existing:
                    conn.execute(text(ddl))


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
