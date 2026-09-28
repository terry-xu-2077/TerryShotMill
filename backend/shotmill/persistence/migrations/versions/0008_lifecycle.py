"""Preserve archive state independently from recoverable deletion."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("projects", "generation_tasks"):
        op.add_column(table, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for table in ("generation_tasks", "projects"):
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "archived_at")
