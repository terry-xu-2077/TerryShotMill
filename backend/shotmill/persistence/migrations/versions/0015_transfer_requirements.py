"""Retain portable import dependency descriptions independently of Job snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column(
        "transfer_requirements", sa.JSON(), nullable=False, server_default="[]",
    ))


def downgrade():
    op.drop_column("projects", "transfer_requirements")
