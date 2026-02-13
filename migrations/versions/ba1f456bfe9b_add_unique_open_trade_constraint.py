"""add unique open trade constraint

Revision ID: ba1f456bfe9b
Revises: 9efab2bddf79
Create Date: 2026-02-04 14:23:33.980682
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'ba1f456bfe9b'
down_revision = '9efab2bddf79'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    indexes = [idx["name"] for idx in inspector.get_indexes("trades")]

    if "uniq_open_trade" not in indexes:
        op.create_index(
            "uniq_open_trade",
            "trades",
            ["ticker", "direction", "created_at"],
            unique=True,
            postgresql_where=sa.text("end_date IS NULL"),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    indexes = [idx["name"] for idx in inspector.get_indexes("trades")]

    if "uniq_open_trade" in indexes:
        op.drop_index("uniq_open_trade", table_name="trades")