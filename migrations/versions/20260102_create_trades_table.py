"""create trades table"""

from alembic import op
import sqlalchemy as sa

revision = "20260102_create_trades_table"
down_revision = "85d3a180c766"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker", sa.String, nullable=False),
        sa.Column("direction", sa.String(16)),
        sa.Column("entry_price", sa.Numeric(18, 8)),
        sa.Column("exit_price", sa.Numeric(18, 8)),
        sa.Column("stop_loss", sa.Numeric(18, 8)),
        sa.Column("leverage", sa.Integer, server_default=sa.text("1")),
        sa.Column("entry_date", sa.DateTime(timezone=True)),
        sa.Column("end_date", sa.DateTime(timezone=True)),
        sa.Column("entry_summary", sa.Text),
        sa.Column("orphan_close", sa.Boolean, server_default=sa.text("false")),
        sa.Column("source", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source_filename", sa.String),
        sa.Column("is_duplicate", sa.Boolean, server_default=sa.text("false")),
    )

def downgrade():
    op.drop_table("trades")
