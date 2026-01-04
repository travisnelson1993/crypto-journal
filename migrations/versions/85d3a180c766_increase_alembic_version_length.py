"""increase alembic_version length

Revision ID: 85d3a180c766
Revises: 20260105_make_alembic_version_text
Create Date: 2026-01-03 15:32:06.241646
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '85d3a180c766'
down_revision = "0001_add_executions_model"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=64),
        existing_type=sa.String(length=32),
        nullable=False,
    )

def downgrade():
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=32),
        existing_type=sa.String(length=64),
        nullable=False,
    )

