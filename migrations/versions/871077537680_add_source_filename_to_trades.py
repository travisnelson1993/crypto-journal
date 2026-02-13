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
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='trades'
            AND column_name='source_filename'
        ) THEN
            ALTER TABLE trades ADD COLUMN source_filename TEXT;
        END IF;
    END$$;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE trades
    DROP COLUMN IF EXISTS source_filename;
    """)

