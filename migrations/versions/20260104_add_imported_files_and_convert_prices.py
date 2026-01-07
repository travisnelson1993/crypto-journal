"""add imported_files table and convert price columns to double precision

Revision ID: 20260104_add_imported_files_and_convert_prices
Revises: 20251230_add_uniq_open_trade_index
Create Date: 2026-01-01 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "20260104_add_imported_files_and_convert_prices"
down_revision = "20251230_add_uniq_open_trade_index"
branch_labels = None
depends_on = None


def _column_is_numeric(colinfo: dict) -> bool:
    """
    Heuristic: inspect the column type string and decide if it's numeric/decimal.
    This is pragmatic and covers common DBMS type representations.
    """
    t = str(colinfo.get("type", "")).lower()
    return "numeric" in t or "decimal" in t or "number" in t


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

    # Gather trades table columns if available
    trades_cols = {}
    try:
        for c in inspector.get_columns("trades"):
            trades_cols[c["name"]] = c
    except Exception:
        trades_cols = {}

    def try_alter(colname: str):
        colinfo = trades_cols.get(colname)
        if not colinfo:
            # Column absent — skip and log
            print(f"[alembic] Skipping ALTER for '{colname}': column not present")
            return
        if not _column_is_numeric(colinfo):
            print(
                f"[alembic] Skipping ALTER for '{colname}': column type is not numeric (detected: {colinfo.get('type')})"
            )
            return
        # Safe to perform the ALTER; let unexpected failures surface so operator sees them
        op.execute(
            f"ALTER TABLE trades ALTER COLUMN {colname} TYPE double precision USING {colname}::double precision;"
        )
        print(f"[alembic] Converted column '{colname}' to double precision")

    # Attempt conversions for specific columns
    try_alter("entry_price")
    try_alter("exit_price")
    try_alter("stop_loss")


def downgrade():
    # Revert price columns back to numeric(20,8) if present
    bind = op.get_bind()
    inspector = inspect(bind)
    trades_cols = {}
    try:
        for c in inspector.get_columns("trades"):
            trades_cols[c["name"]] = c
    except Exception:
        trades_cols = {}

    def try_revert(colname: str):
        colinfo = trades_cols.get(colname)
        if not colinfo:
            print(f"[alembic] Skipping revert for '{colname}': column not present")
            return
        op.execute(
            f"ALTER TABLE trades ALTER COLUMN {colname} TYPE numeric(20,8) USING {colname}::numeric(20,8);"
        )
        print(f"[alembic] Reverted column '{colname}' to numeric(20,8)")

    try_revert("entry_price")
    try_revert("exit_price")
    try_revert("stop_loss")
