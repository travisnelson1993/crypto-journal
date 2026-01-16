"""add equity snapshot fields to trades

Revision ID: b1410c9de4fe
Revises: 2cce8e1faf17
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "b1410c9de4fe"
down_revision = "2cce8e1faf17"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trades",
        sa.Column("account_equity_at_entry", sa.Numeric(18, 8), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("risk_usd_at_entry", sa.Numeric(18, 8), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("risk_pct_at_entry", sa.Numeric(18, 8), nullable=True),
    )


def downgrade():
    op.drop_column("trades", "risk_pct_at_entry")
    op.drop_column("trades", "risk_usd_at_entry")
    op.drop_column("trades", "account_equity_at_entry")
