from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    use_description_for_ai_prompt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cover_asset_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssetModel(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    project_relative_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="reference")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SceneModel(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "order_key", name="uq_scene_project_order"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_key: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TaskModel(Base):
    __tablename__ = "generation_tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "display_order", name="uq_task_project_order"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    script_source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_intent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_prompt_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    generation_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    planned_duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=6.0)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_result_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approved_prompt_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    approved_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_revision_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_view_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="visual")
    ai_view_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="visual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TaskPlacementModel(Base):
    __tablename__ = "task_placements"

    task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    order_key: Mapped[int] = mapped_column(Integer, nullable=False)


class TaskAssetBindingModel(Base):
    __tablename__ = "task_asset_bindings"
    __table_args__ = (
        UniqueConstraint("task_id", "asset_id", "reference", name="uq_task_asset_reference"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True)
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(240), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ContextLinkModel(Base):
    __tablename__ = "generation_context_links"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    target_task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_result_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    final_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    task_content_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    assets_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    generation_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    params_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    runtime_progress: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResultModel(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    video_url: Mapped[str] = mapped_column(String(1200), nullable=False)
    preview_url: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    review_state: Mapped[str] = mapped_column(String(40), nullable=False, default="unreviewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromptRevisionModel(Base):
    __tablename__ = "ai_prompt_revisions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    source_user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    output_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    asset_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    project_background_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    previous_task_summary_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_skill: Mapped[str] = mapped_column(String(100), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_profile_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    elapsed_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_task_summary_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PromptEnhancementBatchModel(Base):
    __tablename__ = "prompt_enhancement_batches"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    running_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromptEnhancementJobModel(Base):
    __tablename__ = "prompt_enhancement_jobs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_enhancement_batches.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    target_skill: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RuntimeControlModel(Base):
    __tablename__ = "runtime_controls"
    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[float | None] = mapped_column(Float, nullable=True)
