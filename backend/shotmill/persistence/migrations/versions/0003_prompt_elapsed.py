"""Persist measured prompt inference time without inventing timing for old revisions."""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_prompt_revisions", sa.Column("elapsed_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_prompt_revisions", "elapsed_seconds")
