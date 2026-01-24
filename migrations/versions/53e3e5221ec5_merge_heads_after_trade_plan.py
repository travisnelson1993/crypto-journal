"""merge heads after trade_plan

Revision ID: 53e3e5221ec5
Revises: 22fa8b390e60, b0e1b4c864bc
Create Date: 2026-01-24 12:21:28.802585
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '53e3e5221ec5'
down_revision = ('22fa8b390e60', 'b0e1b4c864bc')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
