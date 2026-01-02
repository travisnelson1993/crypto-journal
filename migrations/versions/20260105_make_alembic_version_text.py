"""make alembic_version.version_num text

Revision ID: 20260105_make_alembic_version_text
Revises: 20260104_add_imported_files_and_convert_prices
Create Date: 2026-01-05 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260105_make_alembic_version_text"
down_revision = "20260104_add_imported_files_and_convert_prices"
branch_labels = None
depends_on = None


def upgrade():
    # Ensure alembic_version exists and can store long revision strings
    op.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num text NOT NULL);")
    # Try to alter column type to text if it's narrower (safe if already text)
    try:
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE text;")
    except Exception:
        # If alter fails for any reason, ignore to keep migration safe
        pass


def downgrade():
    # No-op downgrade (shrinking the column could break stored revision strings)
    pass
