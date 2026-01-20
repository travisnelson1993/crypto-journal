"""phase 2a journaling models

Revision ID: 92a48923b4c4
Revises: 600f44c88669
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "92a48923b4c4"
down_revision = "600f44c88669"
branch_labels = None
depends_on = None


def upgrade():
    emotional_state = sa.Enum(
        "focused",
        "calm",
        "confident",
        "neutral",
        "impatient",
        "anxious",
        "fearful",
        "greedy",
        "tired",
        "distracted",
        "overconfident",
        name="emotional_state_enum",
    )

    daily_bias = sa.Enum(
        "bullish",
        "bearish",
        "range",
        name="daily_bias_enum",
    )

    op.create_table(
        "daily_journal_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("date", sa.Date, nullable=False, unique=True),
        sa.Column("sleep_quality", sa.Integer, nullable=False),
        sa.Column("energy_level", sa.Integer, nullable=False),
        sa.Column("emotional_state", emotional_state, nullable=False),
        sa.Column("daily_bias", daily_bias, nullable=False),
        sa.Column("confidence", sa.Integer, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "trade_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trade_id", sa.Integer, sa.ForeignKey("trades.id"), nullable=False),
        sa.Column("note_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("trade_notes")
    op.drop_table("daily_journal_entries")

    op.execute("DROP TYPE IF EXISTS emotional_state_enum")
    op.execute("DROP TYPE IF EXISTS daily_bias_enum")
