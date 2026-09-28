"""Imported assets keep descriptive provenance, never source file dependencies."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("assets", sa.Column(
        "provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
    ))


def downgrade():
    op.drop_column("assets", "provenance")
