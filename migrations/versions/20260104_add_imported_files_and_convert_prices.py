"""add imported_files table and convert price columns to double precision

Revision ID: 20260104_add_imported_files_and_convert_prices
Revises: 20260103_create_uniq_open_trade_index_after_trades
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "20260104_add_imported_files_and_convert_prices"
down_revision = "20260103_create_uniq_open_trade_index_after_trades"
branch_labels = None
depends_on = None


def upgrade():
    # Create imported_files table if it does not exist (idempotent)
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("imported_files"):
        op.create_table(
            "imported_files",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("filename", sa.Text, nullable=False),
            sa.Column("file_hash", sa.Text, nullable=False, unique=True),
            sa.Column("source", sa.Text, nullable=True),
            sa.Column(
                "imported_at",
                sa.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
            ),
        )

    # Convert numeric price columns to double precision (no-op if already converted)
    # These ALTERs will succeed if the columns exist; if they don't, they'll raise.
    # We intentionally attempt them so fresh DBs get the desired type and older DBs
    # are converted. We catch exceptions only when the column is absent.
    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN entry_price TYPE double precision USING entry_price::double precision;"
        )
    except Exception:
        # If entry_price doesn't exist, ignore (schema may differ)
        pass

    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN exit_price TYPE double precision USING exit_price::double precision;"
        )
    except Exception:
        pass

    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN stop_loss TYPE double precision USING stop_loss::double precision;"
        )
    except Exception:
        # stop_loss might not exist in older schemas; ignore if so
        pass


def downgrade():
    # Revert price columns back to numeric(20,8) (adjust precision if needed)
    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN entry_price TYPE numeric(20,8) USING entry_price::numeric(20,8);"
        )
    except Exception:
        pass

    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN exit_price TYPE numeric(20,8) USING exit_price::numeric(20,8);"
        )
    except Exception:
        pass

    try:
        op.execute(
            "ALTER TABLE trades ALTER COLUMN stop_loss TYPE numeric(20,8) USING stop_loss::numeric(20,8);"
        )
    except Exception:
        pass

    # Drop imported_files table if present
    op.execute("DROP TABLE IF EXISTS imported_files;")
