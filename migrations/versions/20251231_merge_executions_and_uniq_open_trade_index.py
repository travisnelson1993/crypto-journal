"""merge alembic heads: 0001_add_executions_model + 20251230_add_uniq_open_trade_index

Revision ID: 20251231_merge_executions_and_uniq_open_trade_index
Revises: 0001_add_executions_model, 20251230_add_uniq_open_trade_index
Create Date: 2025-12-31 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = "20251231_merge_executions_and_uniq_open_trade_index"
down_revision = ("0001_add_executions_model", "20251230_add_uniq_open_trade_index")
branch_labels = None
depends_on = None


def upgrade():
    # merge-only migration: no schema changes required
    pass


def downgrade():
    # nothing to do on downgrade for this merge-only revision
    pass
