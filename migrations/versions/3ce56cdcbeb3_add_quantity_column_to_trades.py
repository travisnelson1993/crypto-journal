from alembic import op

revision = "3ce56cdcbeb3"
down_revision = "23a1e90f9720"
branch_labels = None
depends_on = None


def upgrade():
    # NO-OP: quantity already added in 67ccb375b41f
    pass


def downgrade():
    # NO-OP
    pass
