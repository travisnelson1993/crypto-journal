import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Alembic Config object
config = context.config

# Logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import metadata ONLY (safe)
from app.db.database import Base
target_metadata = Base.metadata


def get_database_url() -> str:
    """
    Resolve the database URL in a single, deterministic way.

    Priority:
    1. DATABASE_URL (GitHub Actions / CI)
    2. CRYPTO_JOURNAL_DSN (local dev / importer)
    """
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("CRYPTO_JOURNAL_DSN")
    )


def run_migrations_offline():
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL or CRYPTO_JOURNAL_DSN must be set")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL or CRYPTO_JOURNAL_DSN must be set")

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
