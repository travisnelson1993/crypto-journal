"""baseline schema

Revision ID: 088c8bf376d6
Revises:
Create Date: 2026-01-25 10:08:00.143195
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# NOTE:
# trade_mindset_tags intentionally excluded from baseline schema.
# Journal / mindset features will be added in later migrations once finalized.

revision = '088c8bf376d6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --------------------
    # ENUM TYPES (explicit, idempotent)
    # --------------------
    exec_side = postgresql.ENUM('OPEN', 'CLOSE', name='exec_side')
    exec_direction = postgresql.ENUM('LONG', 'SHORT', name='exec_direction')

    trade_event_type = postgresql.ENUM(
        'hold', 'partial', 'move_sl', 'scale_in', 'exit_early',
        name='trade_event_type_enum'
    )

    trade_event_reason = postgresql.ENUM(
        'plan_based', 'emotion_based', 'external_signal',
        name='trade_event_reason_enum'
    )

    trade_emotion = postgresql.ENUM(
        'calm', 'fear', 'greed', 'doubt', 'impatience',
        name='trade_emotion_enum'
    )

    exit_type = postgresql.ENUM(
        'tp', 'sl', 'manual', 'early',
        name='exit_type_enum'
    )

    violation_reason = postgresql.ENUM(
        'fomo', 'loss_aversion', 'doubt', 'impatience',
        name='violation_reason_enum'
    )

    would_take_again = postgresql.ENUM(
        'yes', 'no', 'with_changes',
        name='would_take_again_enum'
    )

    bind = op.get_bind()
    for enum in [
        exec_side,
        exec_direction,
        trade_event_type,
        trade_event_reason,
        trade_emotion,
        exit_type,
        violation_reason,
        would_take_again,
    ]:
        enum.create(bind, checkfirst=True)

    # --------------------
    # TABLES
    # --------------------
    op.create_table(
        'executions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('source_filename', sa.String(), nullable=True),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('side', sa.Enum('OPEN', 'CLOSE', name='exec_side', create_type=False), nullable=False),
        sa.Column('direction', sa.Enum('LONG', 'SHORT', name='exec_direction', create_type=False), nullable=False),
        sa.Column('price', sa.Numeric(18, 8), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('remaining_qty', sa.Numeric(18, 8), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fee', sa.Numeric(18, 8)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint(
            'source', 'source_filename', 'ticker', 'side', 'direction', 'price', 'quantity', 'timestamp',
            name='uq_execution_dedupe'
        )
    )

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
        sa.Column('created_at', sa.DateTime())
    )
    op.create_index('ix_trade_entry_notes_user_id', 'trade_entry_notes', ['user_id'])

    op.create_table(
        'trade_events',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.Enum(
            'hold', 'partial', 'move_sl', 'scale_in', 'exit_early',
            name='trade_event_type_enum', create_type=False
        ), nullable=False),
        sa.Column('reason', sa.Enum(
            'plan_based', 'emotion_based', 'external_signal',
            name='trade_event_reason_enum', create_type=False
        ), nullable=False),
        sa.Column('emotion', sa.Enum(
            'calm', 'fear', 'greed', 'doubt', 'impatience',
            name='trade_emotion_enum', create_type=False
        )),
        sa.Column('emotion_note', sa.Text()),
        sa.Column('created_at', sa.DateTime())
    )
    op.create_index('ix_trade_events_user_id', 'trade_events', ['user_id'])

    op.create_table(
        'trade_exit_notes',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('trade_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('exit_type', sa.Enum(
            'tp', 'sl', 'manual', 'early',
            name='exit_type_enum', create_type=False
        ), nullable=False),
        sa.Column('plan_followed', sa.Integer(), nullable=False),
        sa.Column('violation_reason', sa.Enum(
            'fomo', 'loss_aversion', 'doubt', 'impatience',
            name='violation_reason_enum', create_type=False
        )),
        sa.Column('would_take_again', sa.Enum(
            'yes', 'no', 'with_changes',
            name='would_take_again_enum', create_type=False
        )),
        sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('trade_id')
    )
    op.create_index('ix_trade_exit_notes_user_id', 'trade_exit_notes', ['user_id'])

    op.create_table(
        'execution_matches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('close_execution_id', sa.Integer(), sa.ForeignKey('executions.id')),
        sa.Column('open_execution_id', sa.Integer(), sa.ForeignKey('executions.id')),
        sa.Column('matched_quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

    op.add_column('trades', sa.Column('quantity', sa.Numeric(18, 8), nullable=False))
    op.alter_column('trades', 'original_quantity', nullable=False)
    op.alter_column('trades', 'entry_price', nullable=False)
    op.alter_column('trades', 'risk_warnings', type_=postgresql.JSONB())
    op.alter_column('trades', 'created_at', nullable=False)

    op.create_index('ix_trades_id', 'trades', ['id'])
    op.create_index('ix_trades_ticker', 'trades', ['ticker'])


def downgrade():
    op.drop_index('ix_trades_ticker', table_name='trades')
    op.drop_index('ix_trades_id', table_name='trades')

    op.alter_column('trades', 'created_at', nullable=True)
    op.alter_column('trades', 'risk_warnings', type_=postgresql.JSON())
    op.alter_column('trades', 'entry_price', nullable=True)
    op.alter_column('trades', 'original_quantity', nullable=True)
    op.drop_column('trades', 'quantity')

    op.drop_table('execution_matches')
    op.drop_table('trade_exit_notes')
    op.drop_table('trade_events')
    op.drop_table('trade_entry_notes')
    op.drop_table('executions')

