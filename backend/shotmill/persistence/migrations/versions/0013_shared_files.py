"""Application-global content objects and explicit logical owners; no legacy file moves."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stored_files",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False, unique=True),
        sa.CheckConstraint("size >= 0", name="ck_stored_file_size"),
    )
    op.create_table(
        "file_references",
        sa.Column("scope_kind", sa.String(32), primary_key=True),
        sa.Column("scope_id", sa.String(80), primary_key=True),
        sa.Column("owner_kind", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.String(80), primary_key=True),
        sa.Column("slot", sa.String(240), primary_key=True),
        sa.Column("sha256", sa.String(64),
                  sa.ForeignKey("stored_files.sha256", ondelete="RESTRICT"), nullable=False),
    )
    op.create_index("ix_file_references_sha256", "file_references", ["sha256"])


def downgrade():
    op.drop_index("ix_file_references_sha256", table_name="file_references")
    op.drop_table("file_references")
    op.drop_table("stored_files")
