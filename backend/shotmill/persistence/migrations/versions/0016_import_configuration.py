"""Imported tasks require explicit destination generation configuration."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generation_tasks", sa.Column(
        "generation_configuration_required", sa.Boolean(), nullable=False, server_default="0",
    ))


def downgrade():
    op.drop_column("generation_tasks", "generation_configuration_required")
