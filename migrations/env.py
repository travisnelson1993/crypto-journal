import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
fileConfig(config.config_file_name)

# Import ONLY metadata (no engine use in env.py)
try:
    from app.db.database import Base
except Exception as e:
    raise ImportError(f"Failed to import Base from app.db.database: {e}")

target_metadata = Base.metadata

# Prefer DATABASE_URL env var if set (CI)
database_url = os.getenv("DATABASE_URL")

if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
else:
    # Fall back to alembic.ini
    if not config.get_main_option("sqlalchemy.url"):
        raise RuntimeError(
            "No DATABASE_URL env var and no sqlalchemy.url in alembic.ini"
        )


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
