"""add trade_lifecycle_events table

Revision ID: 6f0b4ca0dfac
Revises: 088c8bf376d6
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '6f0b4ca0dfac'
down_revision = '088c8bf376d6'
branch_labels = None
depends_on = None


def upgrade():
    # ── ENUM (idempotent) ───────────────────────────────────
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_type
            WHERE typname = 'trade_lifecycle_event_enum'
        ) THEN
            CREATE TYPE trade_lifecycle_event_enum AS ENUM (
                'opened',
                'closed',
                'partial_close',
                'stop_moved'
            );
        END IF;
    END$$;
    """)

    # ── TABLE ───────────────────────────────────────────────
    op.create_table(
        'trade_lifecycle_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column(
            'event_type',
            postgresql.ENUM(
                name='trade_lifecycle_event_enum',
                create_type=False
            ),
            nullable=False
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False
        ),
        sa.ForeignKeyConstraint(
            ['trade_id'],
            ['trades.id'],
            ondelete='CASCADE'
        )
    )


def downgrade():
    op.drop_table('trade_lifecycle_events')

