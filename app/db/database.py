import os
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# -------------------------------------------------------------------
# Database configuration (ASYNC)
# -------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_journal",
)

# Declarative base for models + Alembic
Base = declarative_base()

_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Lazily create the async engine.
    Safe for Alembic imports and FastAPI startup.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """
    Lazily create the async sessionmaker.
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _SessionLocal


# -------------------------------------------------------------------
# Backward-compatible alias for API dependencies
# -------------------------------------------------------------------

AsyncSessionLocal = get_sessionmaker()

