from __future__ import annotations

from shotmill.application.prompt_review import prompt_review_status
from shotmill.domain.entities import AiPromptRevision, Asset, Job, Project, Result, Task
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.frontend_adapter.models import (
    AiPromptRevisionView,
    AssetReferenceItem,
    EditorPreference,
    GenerationSettings,
    GenerationSummary,
    JobView,
    PrimaryResultView,
    ProjectAssetView,
    ProjectRuntimeSummary,
    ProjectSummary,
    ResultView,
    TaskAssetRef,
    TaskEditorView,
    TaskSummary,
)
from shotmill.media.storage import MediaStorage


def _param(params: dict, camel: str, snake: str, default=None):
    if camel in params:
        return params[camel]
    return params.get(snake, default)


def task_status(task: Task) -> str:
    if task.state in {TaskState.QUEUED, TaskState.RUNNING, TaskState.PROMPT_GENERATING}:
        return "running"
    if task.state == TaskState.COMPLETED:
        return "completed"
    if task.state == TaskState.FAILED:
        return "failed"
    return "idle"


def project_status(tasks: list[Task]) -> str:
    statuses = [task_status(task) for task in tasks]
    if "running" in statuses:
        return "running"
    if tasks and all(status == "completed" for status in statuses):
        return "completed"
    if "failed" in statuses:
        return "failed"
    return "idle"


def asset_preview_url(asset: Asset, storage: MediaStorage) -> str | None:
    if asset.thumbnail_path:
        return storage.media_url(asset.project_id, asset.thumbnail_path)
    if asset.media_type == "image":
        return storage.media_url(asset.project_id, asset.project_relative_path)
    return None


def map_asset(asset: Asset, storage: MediaStorage) -> ProjectAssetView:
    return ProjectAssetView(
        id=asset.id,
        name=asset.name,
        originalFileName=asset.original_filename,
        project_relative_path=asset.project_relative_path,
        media_type=asset.media_type,
        category=asset.category,
        tags=asset.tags,
        width=asset.width,
        height=asset.height,
        duration=asset.duration,
        thumbnail_url=asset_preview_url(asset, storage),
    )


def map_asset_reference(asset: Asset, storage: MediaStorage) -> AssetReferenceItem:
    media_type = asset.media_type if asset.media_type in {"image", "video", "audio"} else "other"
    return AssetReferenceItem(
        id=asset.id,
        name=asset.name,
        media_type=media_type,
        category=asset.category,
        preview_url=asset_preview_url(asset, storage),
    )


def map_task_summary(
    task: Task,
    results: list[Result],
    *,
    asset_previews: dict[str, str | None] | None = None,
    has_active_prompt_job: bool = False,
    has_active_video_job: bool = False,
) -> TaskSummary:
    primary = next((result for result in results if result.id == task.primary_result_id), None)
    latest = results[0] if results else None
    preview_source = primary or latest
    params = task.generation_params
    prompt_excerpt = task.final_prompt or task.user_intent or task.summary or ""
    primary_view = None
    if primary:
        primary_view = PrimaryResultView(
            id=primary.id,
            preview_url=primary.preview_url,
            video_url=primary.video_url,
            duration_seconds=primary.metadata.get("durationSeconds"),
        )
    return TaskSummary(
        prompt_source=task.prompt_source.value,
        latest_video_result_id=latest.id if latest else None,
        id=task.id,
        display_number=task.display_order,
        title=task.title,
        prompt_excerpt=prompt_excerpt,
        preview_url=(preview_source.preview_url if preview_source else None)
        or task_reference_preview(task, asset_previews or {}),
        status=task_status(task),
        progress=task.progress if task.state == TaskState.RUNNING else None,
        asset_count=len(task.asset_bindings),
        result_count=len(results),
        duration_seconds=task.planned_duration_seconds,
        generation_summary=GenerationSummary(
            resolution=str(_param(params, "resolution", "resolution", "1080p")),
            quality=str(_param(params, "quality", "quality", "标准")),
        ),
        prompt_review_status=prompt_review_status(task),
        prompt_enhancement_status="running" if has_active_prompt_job else "idle",
        video_generation_status=(
            task.state.value
            if task.state
            in {
                TaskState.QUEUED,
                TaskState.RUNNING,
                TaskState.COMPLETED,
                TaskState.FAILED,
            }
            else "idle"
        ),
        has_active_prompt_job=has_active_prompt_job,
        has_active_video_job=has_active_video_job,
        primary_result=primary_view,
    )


def map_task_editor(task: Task, previous_duration: float | None) -> TaskEditorView:
    params = task.generation_params
    return TaskEditorView(
        id=task.id,
        display_number=task.display_order,
        title=task.title,
        summary=task.summary,
        script_source=task.script_source,
        user_intent=task.user_intent,
        prompt_source=task.prompt_source.value,
        user_prompt=task.user_prompt,
        user_prompt_history=task.user_prompt_history,
        ai_enhanced_prompt=task.ai_prompt,
        final_prompt=task.final_prompt,
        editor_preference=EditorPreference(
            user_view_mode=(
                task.user_view_mode if task.user_view_mode in {"visual", "text"} else "visual"
            ),
            ai_view_mode=task.ai_view_mode if task.ai_view_mode in {"visual", "text"} else "visual",
        ),
        duration_seconds=task.planned_duration_seconds,
        previous_task_duration_seconds=previous_duration,
        generation=GenerationSettings(
            workflow_profile_id=_param(params, "workflowProfileId", "workflow_profile_id"),
            workflow_inputs=_param(params, "workflowInputs", "workflow_inputs"),
            resolution=str(_param(params, "resolution", "resolution", "1080p")),
            quality=str(_param(params, "quality", "quality", "标准")),
            mode=str(_param(params, "mode", "mode", "全能参考")),
            context_mode=str(_param(params, "contextMode", "context_mode", "不承接")),
            context_start_seconds=_param(params, "contextStartSeconds", "context_start_seconds"),
            context_end_seconds=_param(params, "contextEndSeconds", "context_end_seconds"),
            context_duration_seconds=_param(
                params, "contextDurationSeconds", "context_duration_seconds"
            ),
        ),
        asset_bindings=[
            TaskAssetRef(asset_id=binding.asset_id, reference=binding.reference, role=binding.role)
            for binding in task.asset_bindings
        ],
        revision=task.revision,
        prompt_review_status=prompt_review_status(task),
    )


def task_reference_preview(task: Task, asset_previews: dict[str, str | None]) -> str | None:
    for binding in sorted(task.asset_bindings, key=lambda item: item.order_index):
        if preview := asset_previews.get(binding.asset_id):
            return preview
    return None


def map_project_summary(
    project: Project,
    tasks: list[Task],
    asset_count: int,
    results_by_task: dict[str, list[Result]],
    *,
    asset_previews: dict[str, str | None] | None = None,
) -> ProjectSummary:
    cover_url = None
    for task in sorted(tasks, key=lambda item: item.display_order)[:1]:
        results = results_by_task.get(task.id, [])
        primary = next((item for item in results if item.id == task.primary_result_id), None)
        candidate = primary or (results[0] if results else None)
        if candidate and candidate.preview_url:
            cover_url = candidate.preview_url
        else:
            cover_url = task_reference_preview(task, asset_previews or {})
    asset_previews = asset_previews or {}
    cover_url = asset_previews.get(project.cover_asset_id) or cover_url
    return ProjectSummary(
        created_at=project.created_at,
        new_results=[{"video": results[0].id} for results in results_by_task.values() if results],
        id=project.id,
        title=project.title,
        description=project.description,
        completed_task_count=sum(bool(results_by_task.get(task.id)) for task in tasks),
        status=project_status(tasks),
        cover_url=cover_url,
        task_count=len(tasks),
        asset_count=asset_count,
        updated_at=project.updated_at,
    )


def map_runtime(active_job: Job | None, active_task: Task | None) -> ProjectRuntimeSummary:
    if active_job is None or active_task is None:
        return ProjectRuntimeSummary()
    state = "queued" if active_job.status == JobStatus.QUEUED else "running"
    if active_job.status == JobStatus.FAILED:
        state = "failed"
    return ProjectRuntimeSummary(
        active_task_id=active_task.id,
        active_task_title=active_task.title,
        state=state,
        progress=active_task.progress,
    )


def map_revision(revision: AiPromptRevision) -> AiPromptRevisionView:
    return AiPromptRevisionView(
        id=revision.id,
        task_id=revision.task_id,
        created_at=revision.created_at,
        prompt=revision.output_prompt,
        source_user_prompt=revision.source_user_prompt,
        asset_ids=revision.asset_ids,
        include_project_background=revision.project_background_used,
        include_previous_task_summary=revision.previous_task_summary_used,
        previous_task_summary_snapshot=revision.previous_task_summary_snapshot,
        target_skill=revision.target_skill,
        skill_version=revision.skill_version,
        provider_id=revision.provider_profile_id,
        model_id=revision.model,
    )


def map_result(result: Result) -> ResultView:
    return ResultView(
        id=result.id,
        job_id=result.job_id,
        video_url=result.video_url,
        preview_url=result.preview_url,
        metadata=result.metadata,
        review_state=result.review_state,
        created_at=result.created_at,
    )


def map_job(job: Job) -> JobView:
    return JobView(
        id=job.id,
        task_id=job.task_id,
        status=job.status.value,
        provider_job_id=job.provider_job_id,
        submitted_at=job.submitted_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_code=job.error_code,
        error_message=job.error_message,
    )
