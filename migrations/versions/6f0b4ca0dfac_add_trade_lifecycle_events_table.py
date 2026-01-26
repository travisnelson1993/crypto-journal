"""add trade_lifecycle_events table

Revision ID: 6f0b4ca0dfac
Revises: 088c8bf376d6
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "6f0b4ca0dfac"
down_revision = "088c8bf376d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trade_lifecycle_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", sa.Integer(), nullable=False, index=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "opened",
                "closed",
                "partial_close",
                "stop_moved",
                name="trade_lifecycle_event_enum",
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("trade_lifecycle_events", if_exists=True)


