"""add position sizing fields to trades

Revision ID: adc66f16197d
Revises: f6c3f41ed8fb
Create Date: 2026-01-09 05:19:36.251204
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "adc66f16197d"
down_revision = "f6c3f41ed8fb"
branch_labels = None
depends_on = None


def upgrade():
    # ---- position sizing / risk ----
    op.add_column(
        "trades",
        sa.Column("account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("risk_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("qty", sa.Float(), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("notional", sa.Float(), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("fee_paid", sa.Float(), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column(
            "is_partial",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ---- FK to accounts (added separately so SQLite / CI behaves) ----
    op.create_foreign_key(
        "fk_trades_account_id",
        source_table="trades",
        referent_table="accounts",
        local_cols=["account_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_trades_account_id", "trades", type_="foreignkey")

    op.drop_column("trades", "is_partial")
    op.drop_column("trades", "fee_paid")
    op.drop_column("trades", "notional")
    op.drop_column("trades", "qty")
    op.drop_column("trades", "risk_pct")
    op.drop_column("trades", "account_id")
