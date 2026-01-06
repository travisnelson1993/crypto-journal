"""add uniq_open_trade_on_fields index"""

from alembic import op

revision = "20251230_add_uniq_open_trade_index"
down_revision = "20260102_create_trades_table"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_open_trade_on_fields
        ON trades (ticker, direction, entry_date, entry_price)
        WHERE end_date IS NULL;
        """
    )

def downgrade():
    op.execute("DROP INDEX IF EXISTS uniq_open_trade_on_fields;")
