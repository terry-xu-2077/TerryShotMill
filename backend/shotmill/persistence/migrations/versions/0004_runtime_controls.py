"""Persist queue ordering, suspension and runtime history visibility."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_controls",
        sa.Column("job_id", sa.String(), primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_table("runtime_controls")
