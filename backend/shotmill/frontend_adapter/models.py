from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


ProjectStatus = Literal["idle", "running", "completed", "failed"]
TaskStatus = Literal["idle", "running", "completed", "failed"]
RuntimeState = Literal["idle", "queued", "running", "failed"]
PromptReviewStatus = Literal["not_ready", "pending_review", "approved"]
BatchItemState = Literal["queued", "running", "completed", "failed", "skipped", "cancelled"]


class ProjectSummary(ApiModel):
    created_at: datetime | None = None
    new_results: list[dict[str, str]] = Field(default_factory=list)
    generation_warnings: list[str] = Field(default_factory=list)
    id: str
    title: str
    description: str = ""
    completed_task_count: int = 0
    status: ProjectStatus
    cover_url: str | None = None
    task_count: int
    asset_count: int
    updated_at: datetime


class ProjectSettingsView(ApiModel):
    automatic_cover_url: str | None = None
    id: str
    title: str
    description: str
    use_description_for_ai_prompt: bool
    cover_asset_id: str | None = None
    cover_url: str | None = None


class SystemPromptPresetView(ApiModel):
    id: str
    name: str
    prompt: str


class LocalInferenceSettingsView(ApiModel):
    preset_prompt: str
    inference_mode: Literal["one by one", "images", "video"]
    max_frames: int
    max_size: int
    seed_mode: Literal["randomize", "fixed"]
    seed: int
    force_offload: bool
    save_states: bool


class WorkflowNumericBindingView(ApiModel):
    port_id: str = Field(min_length=1)
    source: Literal["constant", "durationSeconds", "frameCount"]
    value: float | None = Field(default=None, allow_inf_nan=False)
    fps: float = Field(default=24, gt=0, le=1000, allow_inf_nan=False)
    frame_multiple: int = Field(default=1, ge=1, le=1024)
    frame_offset: int = Field(default=0, ge=0, le=1023)


class ComfyUIWorkflowProfileView(ApiModel):
    id: str
    name: str
    resolution: str
    quality: str
    workflow_file: str
    enabled: bool
    description: str = ""
    numeric_bindings: list[WorkflowNumericBindingView] = []


class ComfyUISettingsView(ApiModel):
    base_url: str
    root_path: str
    workflow_directory: str
    default_profile_id: str
    workflow_profiles: list[ComfyUIWorkflowProfileView]


class ComfyUIWorkflowPortView(ApiModel):
    name: str
    direction: str
    type: str
    source_node_id: str = ""
    target_node_id: str = ""
    target_slot: str = ""
    target_port: str = ""
    port_name: str = ""


class ComfyUIWorkflowView(ApiModel):
    id: str
    name: str
    file_name: str
    relative_path: str
    format: str
    executable: bool
    has_shotmill_bridge: bool
    inputs: list[ComfyUIWorkflowPortView]
    outputs: list[ComfyUIWorkflowPortView]
    warnings: list[str]


class ComfyUIStatusView(ApiModel):
    connected: bool
    base_url: str
    bridge_node_available: bool
    bridge_state: Literal["connected", "disconnected", "missing", "error"] = "disconnected"
    message: str
    workflows: list[ComfyUIWorkflowView] = []


class ApplicationSettingsView(ApiModel):
    prompt_ai_label: str = "AI 增强服务"
    provider_mode: Literal["local", "api"]
    system_prompt: str
    system_prompt_presets: list[SystemPromptPresetView]
    api_base_url: str
    api_model: str
    api_key: str
    api_supports_native_video: bool
    local_inference: LocalInferenceSettingsView
    comfyui: ComfyUISettingsView


class PrimaryResultView(ApiModel):
    id: str
    preview_url: str | None
    video_url: str
    duration_seconds: float | None = None


class GenerationSummary(ApiModel):
    resolution: str
    quality: str


class TaskTiming(ApiModel):
    generation_progress: dict[str, Any] | None = None
    video_seconds: float | None = None
    video_queue_seconds: float | None = None
    prompt_seconds: float | None = None
    prompt_queue_seconds: float | None = None
    video_running: bool = False
    video_queued: bool = False
    prompt_running: bool = False
    prompt_queued: bool = False
    measured_at: datetime | None = None


class TaskSummary(ApiModel):
    prompt_source: Literal["user", "ai"] = "user"
    generation_status_note: str | None = None
    generation_warnings: list[str] = Field(default_factory=list)
    latest_video_result_id: str | None = None
    latest_prompt_revision_id: str | None = None
    id: str
    display_number: int
    title: str
    prompt_excerpt: str
    preview_url: str | None
    status: TaskStatus
    progress: float | None
    asset_count: int
    result_count: int
    duration_seconds: float
    generation_summary: GenerationSummary
    prompt_review_status: PromptReviewStatus = "not_ready"
    prompt_enhancement_status: str = "idle"
    video_generation_status: str = "idle"
    has_active_prompt_job: bool = False
    has_active_video_job: bool = False
    primary_result: PrimaryResultView | None = None
    timing: TaskTiming = Field(default_factory=TaskTiming)


class RuntimeTaskItem(ApiModel):
    status_note: str | None = None
    continuation_fallback: bool = False
    paused: bool = False
    position: float | None = None
    id: str
    task_id: str
    title: str
    state: BatchItemState
    elapsed_seconds: float | None = None
    error: str | None = None


class PromptBatchRuntime(ApiModel):
    id: str
    created_at: datetime
    state: str
    completed_count: int
    failed_count: int
    cancelled_count: int
    queued_count: int
    running_count: int
    items: list[RuntimeTaskItem]


class ProjectRuntimeSummary(ApiModel):
    active_task_id: str | None = None
    active_task_title: str | None = None
    state: RuntimeState = "idle"
    progress: float | None = None
    prompt_batches: list[PromptBatchRuntime] = Field(default_factory=list)
    video_jobs: list[RuntimeTaskItem] = Field(default_factory=list)


class WorkspaceProject(ApiModel):
    id: str
    title: str


class ProjectRuntimeView(ApiModel):
    project: WorkspaceProject
    runtime: ProjectRuntimeSummary


class ProjectWorkspaceView(ApiModel):
    project: WorkspaceProject
    tasks: list[TaskSummary]
    runtime: ProjectRuntimeSummary


class TaskAssetRef(ApiModel):
    asset_id: str
    reference: str
    role: str | None = None


class WorkflowInputSlot(ApiModel):
    port_id: str
    asset_id: str | None = None
    reference: str


class WorkflowInputSelection(ApiModel):
    workflow_id: str
    slots: list[WorkflowInputSlot] = Field(default_factory=list)


class GenerationSettings(ApiModel):
    workflow_profile_id: str | None = None
    workflow_inputs: WorkflowInputSelection | None = None
    resolution: str = "1080p"
    quality: str = "标准"
    mode: str = "全能参考"
    context_mode: str = "尾帧承接"
    context_start_seconds: float | None = None
    context_end_seconds: float | None = None
    context_duration_seconds: float | None = None


class EditorPreference(ApiModel):
    user_view_mode: Literal["visual", "text"] = "visual"
    ai_view_mode: Literal["visual", "text"] = "visual"


class UserPromptRevisionView(ApiModel):
    id: str
    prompt: str
    created_at: str


class TaskEditorView(ApiModel):
    user_prompt_history: list[UserPromptRevisionView] = []
    id: str
    display_number: int
    title: str
    summary: str
    script_source: str
    user_intent: str
    prompt_source: Literal["user", "ai"]
    user_prompt: str
    ai_enhanced_prompt: str
    final_prompt: str
    editor_preference: EditorPreference
    duration_seconds: float
    previous_task_duration_seconds: float | None
    generation: GenerationSettings
    asset_bindings: list[TaskAssetRef]
    revision: int
    prompt_review_status: PromptReviewStatus = "not_ready"


class PromptReviewItemView(ApiModel):
    task_id: str
    prompt_review_status: PromptReviewStatus
    approved_revision: int | None = None
    approved_at: datetime | None = None


class PromptReviewStateView(ApiModel):
    items: list[PromptReviewItemView]


class AssetReferenceItem(ApiModel):
    id: str
    name: str
    media_type: Literal["image", "video", "audio", "other"]
    category: str
    preview_url: str | None


class ProjectAssetView(ApiModel):
    id: str
    name: str
    original_filename: str = Field(alias="originalFileName")
    project_relative_path: str
    media_type: str
    category: str
    tags: list[str]
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    thumbnail_url: str | None = None


class AiPromptRevisionView(ApiModel):
    id: str
    task_id: str
    created_at: datetime
    prompt: str
    source_user_prompt: str
    asset_ids: list[str]
    include_project_background: bool
    include_previous_task_summary: bool
    previous_task_summary_snapshot: str | None
    target_skill: str
    skill_version: str
    provider_id: str | None
    model_id: str | None


class PromptEnhancementPreviewView(ApiModel):
    preview_id: str
    created_at: datetime
    prompt: str
    target_skill: str
    skill_version: str
    provider_id: str | None
    model_id: str | None


class ResultView(ApiModel):
    id: str
    job_id: str
    video_url: str
    preview_url: str | None
    metadata: dict[str, Any]
    review_state: str
    created_at: datetime


class CancelledVideoJobsView(ApiModel):
    cancelled_job_ids: list[str]


class JobView(ApiModel):
    id: str
    task_id: str
    status: str
    provider_job_id: str | None
    submitted_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None


class BatchPromptEnhancementItemView(ApiModel):
    task_id: str
    state: BatchItemState
    revision_id: str | None = None
    error: str | None = None


class BatchPromptEnhancementResponse(ApiModel):
    batch_id: str
    state: Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
    items: list[BatchPromptEnhancementItemView]


class PromptBatchSkippedItem(ApiModel):
    task_id: str
    reason: Literal["busy", "empty-prompt"]
    message: str


class PromptBatchEligibilityView(ApiModel):
    eligible_task_ids: list[str]
    skipped: list[PromptBatchSkippedItem]


class VideoBatchSkippedItem(ApiModel):
    task_id: str
    reason: str
    code: str | None = None
    message: str | None = None


class VideoBatchEligibilityView(ApiModel):
    warnings: list[dict[str, str]] = Field(default_factory=list)
    eligible_task_ids: list[str]
    skipped: list[VideoBatchSkippedItem]


class VideoBatchResponse(VideoBatchEligibilityView):
    batch_id: str


class ProjectListResponse(ApiModel):
    items: list[ProjectSummary]


class AssetListResponse(ApiModel):
    items: list[ProjectAssetView | AssetReferenceItem]


class PromptRevisionListResponse(ApiModel):
    items: list[AiPromptRevisionView]


class ResultListResponse(ApiModel):
    items: list[ResultView]
