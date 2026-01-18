"""add risk_warnings to trades

Revision ID: 600f44c88669
Revises: b1410c9de4fe
Create Date: 2026-01-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "600f44c88669"
down_revision = "b1410c9de4fe"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "trades",
        sa.Column(
            "risk_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade():
    # SAFETY: only drop if it exists
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'trades'
                    AND column_name = 'risk_warnings'
                ) THEN
                    ALTER TABLE trades DROP COLUMN risk_warnings;
                END IF;
            END
            $$;
            """
        )
