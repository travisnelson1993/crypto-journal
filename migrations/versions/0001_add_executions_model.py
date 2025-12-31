"""add executions, execution_matches, positions tables

Revision ID: 0001_add_executions_model
Revises: 
Create Date: 2025-12-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_add_executions_model'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # executions table
    op.create_table(
        'executions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('source_rowhash', sa.String(length=64), nullable=True, index=False),
        sa.Column('source_execution_id', sa.String(length=128), nullable=True),
        sa.Column('ticker', sa.String(length=32), nullable=False, index=True),
        sa.Column('direction', sa.Enum('LONG', 'SHORT', name='direction_enum'), nullable=False),
        sa.Column('side', sa.Enum('OPEN', 'CLOSE', name='side_enum'), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 8), nullable=False),
        sa.Column('remaining_qty', sa.Numeric(18, 8), nullable=False),
        sa.Column('price', sa.Numeric(30, 12), nullable=True),
        sa.Column('fee', sa.Numeric(30, 12), nullable=True, server_default='0'),
        sa.Column('occurred_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # execution_matches table
    op.create_table(
        'execution_matches',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('open_execution_id', sa.BigInteger(), sa.ForeignKey('executions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('close_execution_id', sa.BigInteger(), sa.ForeignKey('executions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('matched_qty', sa.Numeric(18, 8), nullable=False),
        sa.Column('price', sa.Numeric(30, 12), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # positions table
    op.create_table(
        'positions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('ticker', sa.String(length=32), nullable=False, unique=True),
        sa.Column('quantity', sa.Numeric(30, 12), nullable=False, server_default='0'),
        sa.Column('avg_price', sa.Numeric(30, 12), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Indexes and constraints
    # Unique idempotency index for source/source_filename/source_rowhash if present (Postgres supports partial index)
    if dialect == 'postgresql':
        op.create_index('ix_executions_source_rowhash_unique',
                        'executions',
                        ['source', 'source_filename', 'source_rowhash'],
                        unique=True,
                        postgresql_where=sa.text('source_rowhash IS NOT NULL'))
        # Partial index example: open executions with remaining_qty > 0
        op.create_index('ix_executions_open_remaining',
                        'executions',
                        ['ticker', 'direction', 'side', 'remaining_qty'],
                        postgresql_where=sa.text("side = 'OPEN' AND remaining_qty > 0"))
    else:
        # Best-effort: non unique index (SQLite won't support partial/filtered indexes)
        op.create_index('ix_executions_source_rowhash', 'executions', ['source', 'source_filename', 'source_rowhash'])
        op.create_index('ix_executions_open_remaining', 'executions', ['ticker', 'direction', 'side', 'remaining_qty'])


def downgrade():
    op.drop_index('ix_executions_open_remaining', table_name='executions')
    op.drop_index('ix_executions_source_rowhash', table_name='executions', ignoreerrors=True)
    # Drop tables
    op.drop_table('positions')
    op.drop_table('execution_matches')
    op.drop_table('executions')
    # Drop enums (Postgres)
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS direction_enum')
        op.execute('DROP TYPE IF EXISTS side_enum')
