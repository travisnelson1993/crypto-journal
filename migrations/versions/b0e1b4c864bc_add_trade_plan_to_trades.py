"""add trade_plan to trades

Revision ID: b0e1b4c864bc
Revises: 22fa8b390e60
Create Date: 2026-01-24 12:03:44.625753
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b0e1b4c864bc"
down_revision = "f6c3f41ed8fb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("trade_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trades", "trade_plan")
