from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from shotmill.domain.entities import (
    AiPromptRevision,
    Asset,
    ContextLink,
    Job,
    Project,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Result,
    Task,
    TaskAssetBinding,
)
from shotmill.domain.enums import JobStatus, PromptSource, TaskState
from shotmill.persistence import models


def project_from_model(row: models.ProjectModel) -> Project:
    return Project(
        id=row.id,
        title=row.title,
        description=row.description,
        use_description_for_ai_prompt=row.use_description_for_ai_prompt,
        cover_asset_id=row.cover_asset_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def asset_from_model(row: models.AssetModel) -> Asset:
    return Asset(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        original_filename=row.original_filename,
        project_relative_path=row.project_relative_path,
        media_type=row.media_type,
        category=row.category,
        tags=list(row.tags or []),
        width=row.width,
        height=row.height,
        duration=row.duration,
        hash=row.hash,
        thumbnail_path=row.thumbnail_path,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def task_from_model(session: Session, row: models.TaskModel) -> Task:
    binding_rows = session.scalars(
        select(models.TaskAssetBindingModel)
        .where(models.TaskAssetBindingModel.task_id == row.id)
        .order_by(models.TaskAssetBindingModel.order_index, models.TaskAssetBindingModel.id)
    ).all()
    return Task(
        id=row.id,
        project_id=row.project_id,
        display_order=row.display_order,
        title=row.title,
        summary=row.summary,
        script_source=row.script_source,
        user_intent=row.user_intent,
        user_prompt=row.user_prompt,
        ai_prompt=row.ai_prompt,
        final_prompt=row.final_prompt,
        prompt_source=PromptSource(row.prompt_source),
        generation_params=dict(row.generation_params or {}),
        planned_duration_seconds=row.planned_duration_seconds,
        state=TaskState(row.state),
        progress=row.progress,
        primary_result_id=row.primary_result_id,
        revision=row.revision,
        approved_prompt_source=(
            PromptSource(row.approved_prompt_source) if row.approved_prompt_source else None
        ),
        approved_prompt_hash=row.approved_prompt_hash,
        approved_at=row.approved_at,
        approved_revision_id=row.approved_revision_id,
        user_view_mode=row.user_view_mode,
        ai_view_mode=row.ai_view_mode,
        asset_bindings=[
            TaskAssetBinding(
                asset_id=binding.asset_id,
                reference=binding.reference,
                role=binding.role,
                order_index=binding.order_index,
            )
            for binding in binding_rows
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def job_from_model(row: models.JobModel) -> Job:
    return Job(
        id=row.id,
        project_id=row.project_id,
        task_id=row.task_id,
        status=JobStatus(row.status),
        final_prompt_snapshot=row.final_prompt_snapshot,
        task_content_snapshot=dict(row.task_content_snapshot or {}),
        assets_snapshot=list(row.assets_snapshot or []),
        generation_profile_snapshot=dict(row.generation_profile_snapshot or {}),
        provider_profile_snapshot=dict(row.provider_profile_snapshot or {}),
        params_snapshot=dict(row.params_snapshot or {}),
        context_snapshot=dict(row.context_snapshot or {}),
        execution_context=row.execution_context,
        seed=row.seed,
        provider_job_id=row.provider_job_id,
        submitted_at=row.submitted_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_code=row.error_code,
        error_message=row.error_message,
    )


def result_from_model(row: models.ResultModel) -> Result:
    return Result(
        id=row.id,
        project_id=row.project_id,
        task_id=row.task_id,
        job_id=row.job_id,
        video_url=row.video_url,
        preview_url=row.preview_url,
        metadata=dict(row.metadata_json or {}),
        review_state=row.review_state,
        created_at=row.created_at,
    )


def prompt_revision_from_model(row: models.PromptRevisionModel) -> AiPromptRevision:
    return AiPromptRevision(
        id=row.id,
        project_id=row.project_id,
        task_id=row.task_id,
        source_user_prompt=row.source_user_prompt,
        output_prompt=row.output_prompt,
        asset_ids=list(row.asset_ids or []),
        project_background_used=row.project_background_used,
        previous_task_summary_used=row.previous_task_summary_used,
        target_skill=row.target_skill,
        skill_version=row.skill_version,
        provider_profile_id=row.provider_profile_id,
        model=row.model,
        elapsed_seconds=row.elapsed_seconds,
        previous_task_summary_snapshot=row.previous_task_summary_snapshot,
        created_at=row.created_at,
    )


def context_from_model(row: models.ContextLinkModel) -> ContextLink:
    return ContextLink(
        id=row.id,
        project_id=row.project_id,
        source_task_id=row.source_task_id,
        target_task_id=row.target_task_id,
        kind=row.kind,
        source_result_id=row.source_result_id,
        stale=row.stale,
        created_at=row.created_at,
    )


def prompt_batch_from_model(row: models.PromptEnhancementBatchModel) -> PromptEnhancementBatch:
    return PromptEnhancementBatch(
        id=row.id,
        project_id=row.project_id,
        status=row.status,
        total_count=row.total_count,
        queued_count=row.queued_count,
        running_count=row.running_count,
        completed_count=row.completed_count,
        failed_count=row.failed_count,
        cancelled_count=row.cancelled_count,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def prompt_job_from_model(row: models.PromptEnhancementJobModel) -> PromptEnhancementJob:
    return PromptEnhancementJob(
        id=row.id,
        batch_id=row.batch_id,
        project_id=row.project_id,
        task_id=row.task_id,
        status=JobStatus(row.status),
        source_snapshot=dict(row.source_snapshot or {}),
        context_snapshot=dict(row.context_snapshot or {}),
        provider_profile_snapshot=dict(row.provider_profile_snapshot or {}),
        target_skill=row.target_skill,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        revision_id=row.revision_id,
        error=row.error,
    )
