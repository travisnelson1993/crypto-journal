from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "67ccb375b41f"
down_revision = "85d3a180c766"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("exchange", sa.String(length=50), nullable=True),
        sa.Column(
            "quote_currency",
            sa.String(length=10),
            nullable=False,
            server_default="USDT",
        ),
        sa.Column(
            "equity",
            sa.Float,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("accounts")
