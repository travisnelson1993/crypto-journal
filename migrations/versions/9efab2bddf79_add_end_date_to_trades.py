"""add end_date to trades

Revision ID: 9efab2bddf79
Revises: 6f0b4ca0dfac
Create Date: 2026-02-04 14:16:02.217926
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '9efab2bddf79'
down_revision = '3d2efbe278ef'
branch_labels = None
depends_on = None



def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = [col["name"] for col in inspector.get_columns("trades")]

    if "end_date" not in columns:
        op.add_column(
            "trades",
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = [col["name"] for col in inspector.get_columns("trades")]

    if "end_date" in columns:
        op.drop_column("trades", "end_date")


