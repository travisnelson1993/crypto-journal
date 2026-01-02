"""add uniq_open_trade_on_fields index

Revision ID: 20251230_add_uniq_open_trade_index
Revises:
Create Date: 2025-12-30 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20251230_add_uniq_open_trade_index"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create the partial unique index only if the trades table exists.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "trades" in inspector.get_table_names():
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
            ON trades (ticker, direction, entry_date, entry_price)
            WHERE end_date IS NULL;
            """
        )
    else:
        # trades table not present in this DB state — skip index creation.
        # This keeps the migration safe when run in different order or on fresh DBs.
        pass


def downgrade():
    # Only attempt to drop the index if the table exists.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "trades" in inspector.get_table_names():
        op.execute("DROP INDEX IF EXISTS uniq_open_trade_on_fields;")
