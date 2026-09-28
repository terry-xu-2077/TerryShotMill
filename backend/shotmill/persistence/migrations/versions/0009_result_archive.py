"""Keep archived output records independent from project deletion."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "archived_results",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("source_result_id", sa.String(80), nullable=False, unique=True),
        sa.Column("source_project_id", sa.String(80), nullable=False),
        sa.Column("source_project_title", sa.String(240), nullable=False),
        sa.Column("source_task_id", sa.String(80), nullable=False),
        sa.Column("source_task_title", sa.String(240), nullable=False),
        sa.Column("source_job_id", sa.String(80), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("final_prompt", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("result_metadata", sa.JSON(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_archived_results_source_project_id", "archived_results", ["source_project_id"]
    )


def downgrade():
    op.drop_index("ix_archived_results_source_project_id", table_name="archived_results")
    op.drop_table("archived_results")
