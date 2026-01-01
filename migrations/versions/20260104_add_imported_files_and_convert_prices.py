"""add imported_files table and convert price columns to double precision

Revision ID: 20260104_add_imported_files_and_convert_prices
Revises: 20260103_create_uniq_open_trade_index_after_trades
Create Date: 2026-01-01 00:00:00.000000

NOTE: This migration is idempotent. It uses CREATE TABLE IF NOT EXISTS to allow
re-running on a database where the table may already exist (e.g., if the schema
was applied manually). If you've manually created the schema, you may need to
run `alembic stamp head` to mark this migration as applied.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260104_add_imported_files_and_convert_prices"
down_revision = "20260103_create_uniq_open_trade_index_after_trades"
branch_labels = None
depends_on = None


def upgrade():
    # Create imported_files table (idempotent with IF NOT EXISTS)
    op.execute("""
        CREATE TABLE IF NOT EXISTS imported_files (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            source TEXT,
            imported_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
    """)

    # Convert numeric price columns to double precision (if present)
    # These will work if the columns currently exist as numeric; if already double precision this is a no-op.
    op.execute(
        "ALTER TABLE trades ALTER COLUMN entry_price TYPE double precision USING entry_price::double precision;"
    )
    op.execute(
        "ALTER TABLE trades ALTER COLUMN exit_price TYPE double precision USING exit_price::double precision;"
    )
    # Try to convert stop_loss if present
    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN stop_loss TYPE double precision USING stop_loss::double precision;"
        )
    except Exception:
        # If stop_loss doesn't exist or is already correct, ignore the error
        pass


def downgrade():
    # Revert price columns back to numeric(20,8) (adjust precision/scale if needed)
    op.execute(
        "ALTER TABLE trades ALTER COLUMN entry_price TYPE numeric(20,8) USING entry_price::numeric(20,8);"
    )
    op.execute(
        "ALTER TABLE trades ALTER COLUMN exit_price TYPE numeric(20,8) USING exit_price::numeric(20,8);"
    )
    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN stop_loss TYPE numeric(20,8) USING stop_loss::numeric(20,8);"
        )
    except Exception:
        pass

    # Drop imported_files table (idempotent with IF EXISTS)
    op.execute("DROP TABLE IF EXISTS imported_files;")
