"""baseline schema

Revision ID: 088c8bf376d6
Revises:
Create Date: 2026-01-25 10:08:00.143195
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '088c8bf376d6'
down_revision = None
branch_labels = None
depends_on = None


# ─────────────────────────────────────────────────────────────
# ENUM CREATION (POSTGRES-SAFE)
# ─────────────────────────────────────────────────────────────

def create_enum(name, values):
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
            CREATE TYPE {name} AS ENUM ({vals});
        END IF;
    END$$;
    """)


def upgrade():
    # ── ENUMS ────────────────────────────────────────────────
    create_enum('exec_side', ['OPEN', 'CLOSE'])
    create_enum('exec_direction', ['LONG', 'SHORT'])
    create_enum('trade_event_type_enum',
                ['hold', 'partial', 'move_sl', 'scale_in', 'exit_early'])
    create_enum('trade_event_reason_enum',
                ['plan_based', 'emotion_based', 'external_signal'])
    create_enum('trade_emotion_enum',
                ['calm', 'fear', 'greed', 'doubt', 'impatience'])
    create_enum('exit_type_enum', ['tp', 'sl', 'manual', 'early'])
    create_enum('violation_reason_enum',
                ['fomo', 'loss_aversion', 'doubt', 'impatience'])
    create_enum('would_take_again_enum',
                ['yes', 'no', 'with_changes'])

    # ── TRADES (TRUE BASELINE CREATE) ────────────────────────
    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('direction',
                  postgresql.ENUM(name='exec_direction', create_type=False),
                  nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('original_quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('entry_price', sa.Numeric(18, 8), nullable=False),
        sa.Column('exit_price', sa.Numeric(18, 8)),
        sa.Column('realized_pnl', sa.Numeric(18, 8)),
        sa.Column('created_at',
                  sa.DateTime(timezone=True),
                  server_default=sa.text('now()'),
                  nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True)),
    )

    op.create_index('ix_trades_id', 'trades', ['id'])
    op.create_index('ix_trades_ticker', 'trades', ['ticker'])

    # ── EXECUTIONS ───────────────────────────────────────────
    op.create_table(
        'executions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('source_filename', sa.String()),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('side',
                  postgresql.ENUM(name='exec_side', create_type=False),
                  nullable=False),
        sa.Column('direction',
                  postgresql.ENUM(name='exec_direction', create_type=False),
                  nullable=False),
        sa.Column('price', sa.Numeric(18, 8), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('remaining_qty', sa.Numeric(18, 8), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fee', sa.Numeric(18, 8)),
        sa.Column('created_at',
                  sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
        sa.UniqueConstraint(
            'source', 'source_filename', 'ticker',
            'side', 'direction', 'price',
            'quantity', 'timestamp',
            name='uq_execution_dedupe'
        )
    )

    # ── EXECUTION MATCHES ────────────────────────────────────
    op.create_table(
        'execution_matches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('close_execution_id', sa.Integer()),
        sa.Column('open_execution_id', sa.Integer()),
        sa.Column('matched_quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('created_at',
                  sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['close_execution_id'], ['executions.id']),
        sa.ForeignKeyConstraint(['open_execution_id'], ['executions.id']),
    )

    # ── TRADE ENTRY NOTES ────────────────────────────────────
    op.create_table(
        'trade_entry_notes',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('entry_reasons', postgresql.JSONB(), nullable=False),
        sa.Column('strategy', sa.String()),
        sa.Column('risk_pct', sa.Numeric(5, 2)),
        sa.Column('confidence_at_entry', sa.Integer()),
        sa.Column('optional_comment', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('trade_id')
    )
    op.create_index('ix_trade_entry_notes_user_id',
                    'trade_entry_notes', ['user_id'])

    # ── TRADE EVENTS ─────────────────────────────────────────
    op.create_table(
        'trade_events',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('event_type',
                  postgresql.ENUM(name='trade_event_type_enum',
                                  create_type=False),
                  nullable=False),
        sa.Column('reason',
                  postgresql.ENUM(name='trade_event_reason_enum',
                                  create_type=False),
                  nullable=False),
        sa.Column('emotion',
                  postgresql.ENUM(name='trade_emotion_enum',
                                  create_type=False)),
        sa.Column('emotion_note', sa.Text()),
        sa.Column('created_at', sa.DateTime())
    )
    op.create_index('ix_trade_events_user_id',
                    'trade_events', ['user_id'])

    # ── TRADE EXIT NOTES ─────────────────────────────────────
    op.create_table(
        'trade_exit_notes',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('exit_type',
                  postgresql.ENUM(name='exit_type_enum',
                                  create_type=False),
                  nullable=False),
        sa.Column('plan_followed', sa.Integer(), nullable=False),
        sa.Column('violation_reason',
                  postgresql.ENUM(name='violation_reason_enum',
                                  create_type=False)),
        sa.Column('would_take_again',
                  postgresql.ENUM(name='would_take_again_enum',
                                  create_type=False)),
        sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('trade_id')
    )
    op.create_index('ix_trade_exit_notes_user_id',
                    'trade_exit_notes', ['user_id'])


def downgrade():
    op.drop_table('trade_exit_notes')
    op.drop_table('trade_events')
    op.drop_table('trade_entry_notes')
    op.drop_table('execution_matches')
    op.drop_table('executions')
    op.drop_table('trades')

