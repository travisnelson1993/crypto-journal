import os
import sys
from logging.config import fileConfig

# -------------------------------------------------
# Ensure project root is on PYTHONPATH
# -------------------------------------------------
sys.path.append(os.getcwd())

from alembic import context
from sqlalchemy import create_engine, pool

# -------------------------------------------------
# Alembic Config
# -------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -------------------------------------------------
# 🔒 CRITICAL: Load ALL models before metadata
# -------------------------------------------------
from app.db.database import Base
import app.models  # ✅ REQUIRED — forces model registration

target_metadata = Base.metadata

print(">>> METADATA TABLES LOADED BY ALEMBIC:")
for table in Base.metadata.tables:
    print("   -", table)

# -------------------------------------------------
# Database URL helper
# -------------------------------------------------
def get_database_url() -> str:
    """
    Prefer DATABASE_URL (CI), fallback to CRYPTO_JOURNAL_DSN (local).
    Ensure Alembic uses a synchronous driver.
    """
    url = os.getenv("DATABASE_URL") or os.getenv("CRYPTO_JOURNAL_DSN")
    if not url:
        raise RuntimeError("DATABASE_URL or CRYPTO_JOURNAL_DSN must be set")

    # Convert async URL → sync for Alembic
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)

    return url

# -------------------------------------------------
# Offline migrations
# -------------------------------------------------
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

# -------------------------------------------------
# Online migrations
# -------------------------------------------------
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

# -------------------------------------------------
# Entrypoint
# -------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

