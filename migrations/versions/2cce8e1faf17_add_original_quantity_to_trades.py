"""add original quantity to trades

Revision ID: 2cce8e1faf17
Revises: fcb8554af204
Create Date: 2026-01-12 14:12:34.798612
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2cce8e1faf17"
down_revision = "fcb8554af204"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add column as nullable
    op.add_column(
        "trades",
        sa.Column("original_quantity", sa.Numeric(18, 8), nullable=True),
    )

    # 2. Backfill from quantity
    op.execute(
        "UPDATE trades SET original_quantity = quantity WHERE original_quantity IS NULL"
    )

    # 3. Enforce NOT NULL
    op.alter_column(
        "trades",
        "original_quantity",
        nullable=False,
    )


def downgrade():
    op.drop_column("trades", "original_quantity")

