from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from shotmill.domain.enums import JobStatus, PromptSource, TaskState


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Project:
    id: str
    title: str
    description: str = ""
    use_description_for_ai_prompt: bool = False
    cover_asset_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class Asset:
    id: str
    project_id: str
    name: str
    original_filename: str
    project_relative_path: str
    media_type: str
    category: str = "reference"
    tags: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    hash: str | None = None
    thumbnail_path: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class TaskAssetBinding:
    asset_id: str
    reference: str
    role: str | None = None
    order_index: int = 0


@dataclass(slots=True)
class Task:
    id: str
    project_id: str
    display_order: int
    title: str
    summary: str = ""
    script_source: str = ""
    user_intent: str = ""
    user_prompt: str = ""
    ai_prompt: str = ""
    final_prompt: str = ""
    prompt_source: PromptSource = PromptSource.USER
    generation_params: dict[str, Any] = field(default_factory=dict)
    planned_duration_seconds: float = 6.0
    state: TaskState = TaskState.DRAFT
    progress: float | None = None
    primary_result_id: str | None = None
    revision: int = 1
    approved_prompt_source: PromptSource | None = None
    approved_prompt_hash: str | None = None
    approved_at: datetime | None = None
    approved_revision_id: str | None = None
    user_view_mode: str = "visual"
    ai_view_mode: str = "visual"
    asset_bindings: list[TaskAssetBinding] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def select_final_prompt(self) -> None:
        self.final_prompt = (
            self.ai_prompt if self.prompt_source == PromptSource.AI else self.user_prompt
        )


@dataclass(slots=True)
class ContextLink:
    id: str
    project_id: str
    source_task_id: str
    target_task_id: str
    kind: str
    source_result_id: str | None = None
    stale: bool = False
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class Job:
    id: str
    project_id: str
    task_id: str
    status: JobStatus
    final_prompt_snapshot: str
    task_content_snapshot: dict[str, Any]
    assets_snapshot: list[dict[str, Any]]
    generation_profile_snapshot: dict[str, Any]
    provider_profile_snapshot: dict[str, Any]
    params_snapshot: dict[str, Any]
    context_snapshot: dict[str, Any]
    seed: int | None = None
    provider_job_id: str | None = None
    submitted_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class Result:
    id: str
    project_id: str
    task_id: str
    job_id: str
    video_url: str
    preview_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    review_state: str = "unreviewed"
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class AiPromptRevision:
    id: str
    project_id: str
    task_id: str
    source_user_prompt: str
    output_prompt: str
    asset_ids: list[str]
    project_background_used: bool
    previous_task_summary_used: bool
    target_skill: str
    skill_version: str
    provider_profile_id: str | None = None
    model: str | None = None
    previous_task_summary_snapshot: str | None = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class PromptEnhancementBatch:
    id: str
    project_id: str
    status: str
    total_count: int
    queued_count: int = 0
    running_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class PromptEnhancementJob:
    id: str
    batch_id: str
    project_id: str
    task_id: str
    status: JobStatus
    source_snapshot: dict[str, Any]
    context_snapshot: dict[str, Any]
    provider_profile_snapshot: dict[str, Any]
    target_skill: str
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    revision_id: str | None = None
    error: str | None = None
