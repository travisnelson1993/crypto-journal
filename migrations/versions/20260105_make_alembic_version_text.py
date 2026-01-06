"""make alembic_version.version_num text"""

from alembic import op
import sqlalchemy as sa

revision = "20260105_make_alembic_version_text"
down_revision = "0001_add_executions_model"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.Text(),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )

def downgrade():
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=32),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
