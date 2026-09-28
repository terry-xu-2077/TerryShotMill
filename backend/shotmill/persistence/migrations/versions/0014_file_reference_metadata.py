"""Keep logical media names/types independent from global physical blob paths."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("file_references", sa.Column("original_filename", sa.String(500), nullable=True))
    op.add_column("file_references", sa.Column("mime_type", sa.String(240), nullable=True))


def downgrade():
    op.drop_column("file_references", "mime_type")
    op.drop_column("file_references", "original_filename")
