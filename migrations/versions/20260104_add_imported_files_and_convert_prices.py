"""add imported_files table and convert price columns to double precision

Revision ID: 20260104_add_imported_files_and_convert_prices
Revises: 20260103_create_uniq_open_trade_index_after_trades
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260104_add_imported_files_and_convert_prices"
down_revision = "20260103_create_uniq_open_trade_index_after_trades"
branch_labels = None
depends_on = None


def upgrade():
    # Create imported_files table
    op.create_table(
        "imported_files",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("file_hash", sa.Text, nullable=False, unique=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("imported_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )

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

    # Drop imported_files table
    op.drop_table("imported_files")
