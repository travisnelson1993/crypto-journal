from alembic import op
import sqlalchemy as sa


revision = "67ccb375b41f"
down_revision = "85d3a180c766"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trades",
        sa.Column(
            "account_id",
            sa.Integer,
            sa.ForeignKey("accounts.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "trades",
        sa.Column("risk_pct", sa.Float, nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("risk_usdt", sa.Float, nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("quantity", sa.Float, nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("fees_usdt", sa.Float, nullable=True),
    )


def downgrade():
    op.drop_column("trades", "fees_usdt")
    op.drop_column("trades", "quantity")
    op.drop_column("trades", "risk_usdt")
    op.drop_column("trades", "risk_pct")
    op.drop_column("trades", "account_id")
