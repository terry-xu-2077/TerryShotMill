from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from shotmill.domain.entities import (
    AiPromptRevision,
    ContextLink,
    Job,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Result,
)
from shotmill.domain.enums import JobStatus
from shotmill.persistence import models
from shotmill.persistence.repositories.mappers import (
    context_from_model,
    job_from_model,
    prompt_batch_from_model,
    prompt_job_from_model,
    prompt_revision_from_model,
    result_from_model,
)


class SqlAlchemyJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> Job | None:
        row = self.session.get(models.JobModel, job_id)
        return job_from_model(row) if row else None

    def add(self, job: Job) -> Job:
        self.session.add(
            models.JobModel(
                id=job.id,
                project_id=job.project_id,
                task_id=job.task_id,
                status=job.status.value,
                final_prompt_snapshot=job.final_prompt_snapshot,
                task_content_snapshot=job.task_content_snapshot,
                assets_snapshot=job.assets_snapshot,
                generation_profile_snapshot=job.generation_profile_snapshot,
                provider_profile_snapshot=job.provider_profile_snapshot,
                params_snapshot=job.params_snapshot,
                context_snapshot=job.context_snapshot,
                execution_context=job.execution_context,
                seed=job.seed,
                provider_job_id=job.provider_job_id,
                submitted_at=job.submitted_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                error_code=job.error_code,
                error_message=job.error_message,
            )
        )
        self.session.flush()
        return job

    def update_runtime(self, job: Job) -> Job:
        row = self.session.get(models.JobModel, job.id)
        if row is None:
            raise KeyError(job.id)
        row.status = job.status.value
        row.provider_job_id = job.provider_job_id
        row.started_at = job.started_at
        row.completed_at = job.completed_at
        row.error_code = job.error_code
        row.error_message = job.error_message
        self.session.flush()
        return job

    def bind_execution_context(self, job_id: str, context: dict) -> dict:
        row = self.session.get(models.JobModel, job_id)
        if row is None:
            raise KeyError(job_id)
        if row.execution_context is None:
            row.execution_context = context
            self.session.flush()
        return dict(row.execution_context)

    def list_by_task(self, task_id: str) -> list[Job]:
        rows = self.session.scalars(
            select(models.JobModel)
            .where(models.JobModel.task_id == task_id)
            .order_by(models.JobModel.submitted_at.desc())
        ).all()
        return [job_from_model(row) for row in rows]

    def list_active(self) -> list[Job]:
        rows = self.session.scalars(
            select(models.JobModel).where(models.JobModel.status.in_([
                JobStatus.QUEUED.value, JobStatus.RUNNING.value,
            ])).order_by(models.JobModel.submitted_at, models.JobModel.id)
        ).all()
        return [job_from_model(row) for row in rows]

    def latest_active_by_project(self, project_id: str) -> Job | None:
        row = self.session.scalar(
            select(models.JobModel)
            .where(
                models.JobModel.project_id == project_id,
                models.JobModel.status.in_([
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ]),
            )
            .order_by(models.JobModel.submitted_at.desc())
            .limit(1)
        )
        return job_from_model(row) if row else None

    def active_task_ids_by_project(self, project_id: str) -> set[str]:
        rows = self.session.scalars(
            select(models.JobModel.task_id).where(
                models.JobModel.project_id == project_id,
                models.JobModel.status.in_([
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ]),
            )
        ).all()
        return set(rows)


class SqlAlchemyResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, result_id: str) -> Result | None:
        row = self.session.get(models.ResultModel, result_id)
        return result_from_model(row) if row else None

    def add(self, result: Result) -> Result:
        self.session.add(
            models.ResultModel(
                id=result.id,
                project_id=result.project_id,
                task_id=result.task_id,
                job_id=result.job_id,
                video_url=result.video_url,
                preview_url=result.preview_url,
                metadata_json=result.metadata,
                review_state=result.review_state,
                created_at=result.created_at,
            )
        )
        self.session.flush()
        return result

    def list_by_task(self, task_id: str) -> list[Result]:
        rows = self.session.scalars(
            select(models.ResultModel)
            .where(models.ResultModel.task_id == task_id)
            .order_by(models.ResultModel.created_at.desc())
        ).all()
        return [result_from_model(row) for row in rows]

    def count_by_task(self, task_id: str) -> int:
        value = self.session.scalar(
            select(func.count())
            .select_from(models.ResultModel)
            .where(models.ResultModel.task_id == task_id)
        )
        return int(value or 0)


class SqlAlchemyPromptRevisionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, revision_id: str) -> AiPromptRevision | None:
        row = self.session.get(models.PromptRevisionModel, revision_id)
        return prompt_revision_from_model(row) if row else None

    def add(self, revision: AiPromptRevision) -> AiPromptRevision:
        self.session.add(
            models.PromptRevisionModel(
                id=revision.id,
                project_id=revision.project_id,
                task_id=revision.task_id,
                source_user_prompt=revision.source_user_prompt,
                output_prompt=revision.output_prompt,
                asset_ids=revision.asset_ids,
                project_background_used=revision.project_background_used,
                previous_task_summary_used=revision.previous_task_summary_used,
                target_skill=revision.target_skill,
                skill_version=revision.skill_version,
                provider_profile_id=revision.provider_profile_id,
                model=revision.model,
                elapsed_seconds=revision.elapsed_seconds,
                previous_task_summary_snapshot=revision.previous_task_summary_snapshot,
                created_at=revision.created_at,
            )
        )
        self.session.flush()
        return revision

    def list_by_task(self, task_id: str) -> list[AiPromptRevision]:
        rows = self.session.scalars(
            select(models.PromptRevisionModel)
            .where(models.PromptRevisionModel.task_id == task_id)
            .order_by(models.PromptRevisionModel.created_at.desc())
        ).all()
        return [prompt_revision_from_model(row) for row in rows]


class SqlAlchemyPromptEnhancementBatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, batch_id: str) -> PromptEnhancementBatch | None:
        row = self.session.get(models.PromptEnhancementBatchModel, batch_id)
        return prompt_batch_from_model(row) if row else None

    def list_by_project(self, project_id: str) -> list[PromptEnhancementBatch]:
        rows = self.session.scalars(
            select(models.PromptEnhancementBatchModel)
            .where(models.PromptEnhancementBatchModel.project_id == project_id)
            .order_by(models.PromptEnhancementBatchModel.created_at.desc())
        ).all()
        return [prompt_batch_from_model(row) for row in rows]

    def add(self, batch: PromptEnhancementBatch) -> PromptEnhancementBatch:
        self.session.add(
            models.PromptEnhancementBatchModel(
                id=batch.id,
                project_id=batch.project_id,
                status=batch.status,
                total_count=batch.total_count,
                queued_count=batch.queued_count,
                running_count=batch.running_count,
                completed_count=batch.completed_count,
                failed_count=batch.failed_count,
                cancelled_count=batch.cancelled_count,
                created_at=batch.created_at,
                started_at=batch.started_at,
                finished_at=batch.finished_at,
            )
        )
        self.session.flush()
        return batch

    def update(self, batch: PromptEnhancementBatch) -> PromptEnhancementBatch:
        row = self.session.get(models.PromptEnhancementBatchModel, batch.id)
        if row is None:
            raise KeyError(batch.id)
        row.status = batch.status
        row.total_count = batch.total_count
        row.queued_count = batch.queued_count
        row.running_count = batch.running_count
        row.completed_count = batch.completed_count
        row.failed_count = batch.failed_count
        row.cancelled_count = batch.cancelled_count
        row.started_at = batch.started_at
        row.finished_at = batch.finished_at
        self.session.flush()
        return batch


class SqlAlchemyPromptEnhancementJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> PromptEnhancementJob | None:
        row = self.session.get(models.PromptEnhancementJobModel, job_id)
        return prompt_job_from_model(row) if row else None

    def list_by_task(self, task_id: str) -> list[PromptEnhancementJob]:
        rows = self.session.scalars(
            select(models.PromptEnhancementJobModel)
            .where(models.PromptEnhancementJobModel.task_id == task_id)
            .order_by(models.PromptEnhancementJobModel.created_at)
        ).all()
        return [prompt_job_from_model(row) for row in rows]

    def add(self, job: PromptEnhancementJob) -> PromptEnhancementJob:
        self.session.add(
            models.PromptEnhancementJobModel(
                id=job.id,
                batch_id=job.batch_id,
                project_id=job.project_id,
                task_id=job.task_id,
                status=job.status.value,
                source_snapshot=job.source_snapshot,
                context_snapshot=job.context_snapshot,
                provider_profile_snapshot=job.provider_profile_snapshot,
                target_skill=job.target_skill,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                revision_id=job.revision_id,
                error=job.error,
            )
        )
        self.session.flush()
        return job

    def update(self, job: PromptEnhancementJob) -> PromptEnhancementJob:
        row = self.session.get(models.PromptEnhancementJobModel, job.id)
        if row is None:
            raise KeyError(job.id)
        row.status = job.status.value
        row.source_snapshot = job.source_snapshot
        row.context_snapshot = job.context_snapshot
        row.provider_profile_snapshot = job.provider_profile_snapshot
        row.target_skill = job.target_skill
        row.started_at = job.started_at
        row.finished_at = job.finished_at
        row.revision_id = job.revision_id
        row.error = job.error
        self.session.flush()
        return job

    def list_by_batch(self, batch_id: str) -> list[PromptEnhancementJob]:
        rows = self.session.scalars(
            select(models.PromptEnhancementJobModel)
            .where(models.PromptEnhancementJobModel.batch_id == batch_id)
            .order_by(models.PromptEnhancementJobModel.created_at)
        ).all()
        return [prompt_job_from_model(row) for row in rows]

    def list_active(self) -> list[PromptEnhancementJob]:
        rows = self.session.scalars(
            select(models.PromptEnhancementJobModel)
            .where(
                models.PromptEnhancementJobModel.status.in_([
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ])
            )
            .order_by(models.PromptEnhancementJobModel.created_at)
        ).all()
        return [prompt_job_from_model(row) for row in rows]

    def active_task_ids_by_project(self, project_id: str) -> set[str]:
        rows = self.session.scalars(
            select(models.PromptEnhancementJobModel.task_id).where(
                models.PromptEnhancementJobModel.project_id == project_id,
                models.PromptEnhancementJobModel.status.in_([
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                ]),
            )
        ).all()
        return set(rows)


class SqlAlchemyContextRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_target(self, task_id: str) -> list[ContextLink]:
        rows = self.session.scalars(
            select(models.ContextLinkModel).where(
                models.ContextLinkModel.target_task_id == task_id
            )
        ).all()
        return [context_from_model(row) for row in rows]

    def replace_for_target(self, task_id: str, links: list[ContextLink]) -> None:
        self.session.execute(
            delete(models.ContextLinkModel).where(
                models.ContextLinkModel.target_task_id == task_id
            )
        )
        for link in links:
            self.session.add(
                models.ContextLinkModel(
                    id=link.id,
                    project_id=link.project_id,
                    source_task_id=link.source_task_id,
                    target_task_id=link.target_task_id,
                    kind=link.kind,
                    source_result_id=link.source_result_id,
                    stale=link.stale,
                    created_at=link.created_at,
                )
            )
        self.session.flush()

    def mark_stale_by_source(self, task_id: str) -> int:
        result = self.session.execute(
            update(models.ContextLinkModel)
            .where(models.ContextLinkModel.source_task_id == task_id)
            .values(stale=True)
        )
        self.session.flush()
        return int(result.rowcount or 0)
