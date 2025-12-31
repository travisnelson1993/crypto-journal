from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

# Set your DB URL here (this is the existing default; CI or local env may override via DATABASE_URL)
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_journal"

# Create async engine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True,
)

# Async session factory
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

# Export declarative Base for models and alembic
Base = declarative_base()
