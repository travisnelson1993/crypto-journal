import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import metadata only
from app.db.database import Base

target_metadata = Base.metadata


def get_database_url() -> str:
    # Prefer DATABASE_URL (CI), fallback to CRYPTO_JOURNAL_DSN (local).
    url = os.getenv("DATABASE_URL") or os.getenv("CRYPTO_JOURNAL_DSN")
    if not url:
        raise RuntimeError("DATABASE_URL or CRYPTO_JOURNAL_DSN must be set")

    # Alembic MUST use a sync driver.
    # If app uses asyncpg, convert to a sync psycopg2-style URL.
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)

    return url


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_database_url()
    engine = create_engine(url, poolclass=pool.NullPool)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
