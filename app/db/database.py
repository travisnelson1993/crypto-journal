import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:55433/crypto_journal",
)

_engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


# -------------------------------------------------
# Engine
# -------------------------------------------------
def get_async_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            echo=True,  # keep on during dev
        )
    return _engine


# -------------------------------------------------
# Sessionmaker
# -------------------------------------------------
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global AsyncSessionLocal
    if AsyncSessionLocal is None:
        AsyncSessionLocal = async_sessionmaker(
            bind=get_async_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return AsyncSessionLocal


# -------------------------------------------------
# FastAPI dependency (canonical)
# -------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    sessionmaker = get_async_sessionmaker()
    async with sessionmaker() as session:
        yield session


# -------------------------------------------------
# 🔁 Compatibility alias (DO NOT REMOVE YET)
# -------------------------------------------------
# Some routers import `get_async_session`
# This keeps everything working without refactors
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session
