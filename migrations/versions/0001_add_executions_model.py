from alembic import op
import sqlalchemy as sa

revision = "0001_add_executions_model"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("source_filename", sa.String),
        sa.Column("ticker", sa.String, nullable=False),
        sa.Column("side", sa.Enum("OPEN", "CLOSE", name="exec_side"), nullable=False),
        sa.Column("direction", sa.Enum("LONG", "SHORT", name="exec_direction"), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fee", sa.Numeric(18, 8), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "execution_matches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("close_execution_id", sa.Integer, sa.ForeignKey("executions.id")),
        sa.Column("open_execution_id", sa.Integer, sa.ForeignKey("executions.id")),
        sa.Column("matched_quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("execution_matches")
    op.drop_table("executions")
