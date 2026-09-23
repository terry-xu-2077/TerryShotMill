"""Persist observed video execution telemetry separately from snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("runtime_progress", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("jobs", "runtime_progress")
