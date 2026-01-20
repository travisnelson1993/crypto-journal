"""Phase 2B: trade note type enum

Revision ID: 22fa8b390e60
Revises: 92a48923b4c4
Create Date: 2026-01-20 09:25:49.497991
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '22fa8b390e60'
down_revision = '92a48923b4c4'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create ENUM type
    op.execute(
        "CREATE TYPE trade_note_type_enum AS ENUM ('entry', 'mid', 'exit')"
    )

    # 2. Convert column from VARCHAR -> ENUM
    op.alter_column(
        "trade_notes",
        "note_type",
        type_=sa.Enum(name="trade_note_type_enum"),
        postgresql_using="note_type::trade_note_type_enum",
        nullable=False,
    )


def downgrade():
    # 1. Convert ENUM back to VARCHAR
    op.alter_column(
        "trade_notes",
        "note_type",
        type_=sa.String(),
        nullable=False,
    )

    # 2. Drop ENUM type
    op.execute("DROP TYPE trade_note_type_enum")
