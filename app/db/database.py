from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/crypto_journal"

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
