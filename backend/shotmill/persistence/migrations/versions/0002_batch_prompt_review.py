# ruff: noqa
"""batch prompt review

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_tasks",
        sa.Column("approved_prompt_source", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("approved_prompt_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "generation_tasks",
        sa.Column("approved_revision_id", sa.String(length=80), nullable=True),
    )

    op.create_table(
        "prompt_enhancement_batches",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("queued_count", sa.Integer(), nullable=False),
        sa.Column("running_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("cancelled_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_prompt_enhancement_batches_project_id"),
        "prompt_enhancement_batches",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "prompt_enhancement_jobs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("batch_id", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("task_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider_profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("target_skill", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision_id", sa.String(length=80), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["prompt_enhancement_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["generation_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_prompt_enhancement_jobs_batch_id"),
        "prompt_enhancement_jobs",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_prompt_enhancement_jobs_project_id"),
        "prompt_enhancement_jobs",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_prompt_enhancement_jobs_task_id"),
        "prompt_enhancement_jobs",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_prompt_enhancement_jobs_task_id"), table_name="prompt_enhancement_jobs")
    op.drop_index(
        op.f("ix_prompt_enhancement_jobs_project_id"),
        table_name="prompt_enhancement_jobs",
    )
    op.drop_index(op.f("ix_prompt_enhancement_jobs_batch_id"), table_name="prompt_enhancement_jobs")
    op.drop_table("prompt_enhancement_jobs")
    op.drop_index(
        op.f("ix_prompt_enhancement_batches_project_id"),
        table_name="prompt_enhancement_batches",
    )
    op.drop_table("prompt_enhancement_batches")
    op.drop_column("generation_tasks", "approved_revision_id")
    op.drop_column("generation_tasks", "approved_at")
    op.drop_column("generation_tasks", "approved_prompt_hash")
    op.drop_column("generation_tasks", "approved_prompt_source")
