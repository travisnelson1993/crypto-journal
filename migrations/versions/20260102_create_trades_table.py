"""create trades table

Revision ID: 20260102_create_trades_table
Revises: 20260101_ensure_uniq_open_trade_index
Create Date: 2026-01-02 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260102_create_trades_table"
down_revision = "20260101_ensure_uniq_open_trade_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker", sa.String, nullable=False),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("entry_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("exit_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("stop_loss", sa.Numeric(18, 8), nullable=True),
        sa.Column("leverage", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("entry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_summary", sa.Text, nullable=True),
        sa.Column(
            "orphan_close", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("source", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("source_filename", sa.String, nullable=True),
        sa.Column(
            "is_duplicate", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade():
    op.drop_table("trades")
