"""Bind deferred generation context once without changing submitted snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("execution_context", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("jobs", "execution_context")
