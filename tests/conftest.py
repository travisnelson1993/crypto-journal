import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
import pytest_asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from app.db.database import Base


# ----------------------------
# Async DB (canonical for async tests / API tests)
# ----------------------------
ASYNC_TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = create_async_engine(
        ASYNC_TEST_DB,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncSession:
    SessionLocal = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with SessionLocal() as session:
        yield session


# Legacy alias for older tests that expect db_session
@pytest_asyncio.fixture
async def db_session(async_session):
    return async_session


# ----------------------------
# Sync DB (only if you still have truly sync DB unit tests)
# ----------------------------
SYNC_TEST_DB = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def sync_engine():
    engine = create_engine(
        SYNC_TEST_DB,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def sync_session(sync_engine) -> Session:
    SessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ----------------------------
# FastAPI dependency override (prevents Postgres hits)
# Keep here so API tests don't need their own conftest.
# ----------------------------
@pytest_asyncio.fixture(autouse=True)
async def _override_get_db_for_api_tests(async_session):
    """
    Any test that imports/uses FastAPI app routes must not touch Postgres.
    This is safe to apply globally; non-API tests won't care.
    """
    try:
        from app.main import app
        from app.db.database import get_db
    except Exception:
        # If app import isn't available in some contexts, don't block unit tests.
        yield
        return

    async def _get_db():
        yield async_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield
    finally:
        app.dependency_overrides.clear()

