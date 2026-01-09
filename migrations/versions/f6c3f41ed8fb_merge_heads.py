"""merge heads

Revision ID: f6c3f41ed8fb
Revises: 20260104_add_imported_files_and_convert_prices, 67ccb375b41f
Create Date: 2026-01-08 12:54:52.456265
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6c3f41ed8fb"
down_revision = ("20260104_add_imported_files_and_convert_prices", "67ccb375b41f")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
