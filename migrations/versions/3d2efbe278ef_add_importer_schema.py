"""add importer schema

Revision ID: 3d2efbe278ef
Revises: b9b7f671cdfa
Create Date: 2026-02-13
"""

from alembic import op
import sqlalchemy as sa

revision = "3d2efbe278ef"
down_revision = "6f0b4ca0dfac"
branch_labels = None
depends_on = None


def upgrade():

    # Add source column if missing
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='trades' AND column_name='source'
        ) THEN
            ALTER TABLE trades ADD COLUMN source VARCHAR;
        END IF;
    END$$;
    """)

    # Add source_filename column if missing
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='trades' AND column_name='source_filename'
        ) THEN
            ALTER TABLE trades ADD COLUMN source_filename VARCHAR;
        END IF;
    END$$;
    """)

    # Create imported_files table with file_hash
    op.execute("""
    CREATE TABLE IF NOT EXISTS imported_files (
        id SERIAL PRIMARY KEY,
        source VARCHAR NOT NULL,
        filename VARCHAR NOT NULL,
        file_hash VARCHAR NOT NULL,
        imported_at TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT uq_imported_file_hash UNIQUE (file_hash)
    );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS imported_files;")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS source_filename;")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS source;")
