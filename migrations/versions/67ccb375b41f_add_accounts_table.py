from alembic import op
import sqlalchemy as sa

revision = "67ccb375b41f"
down_revision = "85d3a180c766"
branch_labels = None
depends_on = None


def upgrade():
    # 1️ Create accounts table FIRST
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # 2️ Add account_id to trades
    op.add_column(
        "trades",
        sa.Column("account_id", sa.Integer(), nullable=True),
    )

    # 3️ Add foreign key AFTER both tables exist
    op.create_foreign_key(
        "fk_trades_account",
        "trades",
        "accounts",
        ["account_id"],
        ["id"],
    )

    # 4️ Other sizing fields
    op.add_column("trades", sa.Column("risk_pct", sa.Float, nullable=True))
    op.add_column("trades", sa.Column("risk_usdt", sa.Float, nullable=True))
    op.add_column("trades", sa.Column("quantity", sa.Float, nullable=True))
    op.add_column("trades", sa.Column("fees_usdt", sa.Float, nullable=True))


def downgrade():
    op.drop_column("trades", "fees_usdt")
    op.drop_column("trades", "quantity")
    op.drop_column("trades", "risk_usdt")
    op.drop_column("trades", "risk_pct")
    op.drop_constraint("fk_trades_account", "trades", type_="foreignkey")
    op.drop_column("trades", "account_id")
    op.drop_table("accounts")
