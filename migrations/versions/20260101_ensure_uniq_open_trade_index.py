"""ensure uniq_open_trade_on_fields index exists

Revision ID: 20260101_ensure_uniq_open_trade_index
Revises: 20251231_merge_executions_and_uniq_open_trade_index
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260101_ensure_uniq_open_trade_index"
down_revision = "20251231_merge_executions_and_uniq_open_trade_index"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # only create the index if the table exists
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
