"""Persist post-commit cleanup so failures and restarts are recoverable."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pending_file_cleanup",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("paths", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM pending_file_cleanup")):
        raise RuntimeError("Cannot discard pending file cleanup")
    op.drop_table("pending_file_cleanup")
