"""add realized pnl to trades

Revision ID: fcb8554af204
Revises: 3ce56cdcbeb3
Create Date: 2026-01-11 16:38:50.127693
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "fcb8554af204"
down_revision = "3ce56cdcbeb3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trades",
        sa.Column("realized_pnl", sa.Numeric(18, 8), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("realized_pnl_pct", sa.Numeric(18, 8), nullable=True),
    )


def downgrade():
    op.drop_column("trades", "realized_pnl_pct")
    op.drop_column("trades", "realized_pnl")
