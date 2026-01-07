import os
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

# Export declarative Base for models and Alembic
Base = declarative_base()

# Default DB URL (CI/local override via env var)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_journal",
)

_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """
    Lazily create the async engine.
    Safe for Alembic imports.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """
    Lazily create sessionmaker.
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _SessionLocal
