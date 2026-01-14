from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "23a1e90f9720"
down_revision = "adc66f16197d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trades",
        sa.Column("fee", sa.Numeric(18, 8), nullable=True),
    )


def downgrade():
    op.drop_column("trades", "fee")

