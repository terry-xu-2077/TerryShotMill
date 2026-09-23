"""Persist user prompt edit history independently of generation parameters."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "generation_tasks",
        sa.Column("user_prompt_history", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("generation_tasks", "user_prompt_history")
