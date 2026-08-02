"""Test configuration and fixtures.

Environment is set BEFORE importing any app module so that settings pick up a
throwaway SQLite file and the deterministic mock LLM provider.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Must run before app.config / app.db.database import their settings.
_TMP_DB = Path(tempfile.gettempdir()) / "support_triage_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["LLM_PROVIDER"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal, engine, init_db  # noqa: E402
from app.db.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """Recreate all tables before each test for isolation."""
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
