import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ------------------------------------------------------------------
# Base (shared by sync + async)
# ------------------------------------------------------------------
Base = declarative_base()

# ------------------------------------------------------------------
# Database URLs
# ------------------------------------------------------------------

SYNC_DATABASE_URL = os.getenv(
    "CRYPTO_JOURNAL_DSN",
    "postgresql://postgres:postgres@localhost:5432/crypto_journal",
)

ASYNC_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_journal",
)

# ------------------------------------------------------------------
# Sync engine (Alembic, scripts)
# ------------------------------------------------------------------

engine = create_engine(
    SYNC_DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ------------------------------------------------------------------
# Async engine (FastAPI)
# ------------------------------------------------------------------

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
