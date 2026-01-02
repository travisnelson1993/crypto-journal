"""create uniq_open_trade_on_fields index (after trades table)

Revision ID: 20260103_create_uniq_open_trade_index_after_trades
Revises: 20260102_create_trades_table
Create Date: 2026-01-03 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260103_create_uniq_open_trade_index_after_trades"
down_revision = "20260102_create_trades_table"
branch_labels = None
depends_on = None


def upgrade():
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


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "trades" in inspector.get_table_names():
        op.execute("DROP INDEX IF EXISTS uniq_open_trade_on_fields;")
