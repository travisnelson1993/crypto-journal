"""add source_filename to trades

Revision ID: 871077537680
Revises: ba1f456bfe9b
Create Date: 2026-02-05 08:12:17.088715
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '871077537680'
down_revision = 'ba1f456bfe9b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trades",
        sa.Column("source_filename", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("trades", "source_filename")
