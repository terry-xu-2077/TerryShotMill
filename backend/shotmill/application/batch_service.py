from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationService
from shotmill.application.managed_queue import ManagedQueue
from shotmill.application.prompt_enhancement_service import (
    EnhancementContextOptions,
    EnhancementMedia,
    PromptEnhancementService,
)
from shotmill.domain.entities import (
    AiPromptRevision,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Task,
    new_id,
    utcnow,
)
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError, ShotMillError


@dataclass(frozen=True, slots=True)
class BatchPromptItemResult:
    task_id: str
    state: str
    revision_id: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BatchPromptResult:
    batch_id: str
    state: str
    items: list[BatchPromptItemResult]


@dataclass(frozen=True, slots=True)
class VideoBatchSkipped:
    task_id: str
    reason: str
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class VideoBatchEligibility:
    eligible_task_ids: list[str]
    skipped: list[VideoBatchSkipped]
    warnings: list[dict[str, str]]


@dataclass(frozen=True, slots=True)
class VideoBatchResult(VideoBatchEligibility):
    batch_id: str


@dataclass(frozen=True, slots=True)
class PromptBatchSkipped:
    task_id: str
    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class PromptBatchEligibility:
    eligible_task_ids: list[str]
    skipped: list[PromptBatchSkipped]


@dataclass(frozen=True, slots=True)
class SinglePromptInput:
    user_prompt: str
    media: tuple[EnhancementMedia, ...]
    duration_seconds: float
    mode: str
    context_mode: str | None


class BatchProductionService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        prompt_service: PromptEnhancementService,
        generation_service: GenerationService,
        *,
        events: ProjectEventBus | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.prompt_service = prompt_service
        self.generation_service = generation_service
        self.events = events
        self.prompt_queue: PromptEnhancementQueue | None = None

    def attach_queue(self, queue: PromptEnhancementQueue) -> None:
        self.prompt_queue = queue

    async def enhance_single(
        self,
        project_id: str,
        task_id: str,
        *,
        target: str,
        user_prompt: str,
        media: tuple[EnhancementMedia, ...],
        context: EnhancementContextOptions,
        duration_seconds: float,
        mode: str,
        context_mode: str | None,
    ) -> AiPromptRevision:
        # Keep the synchronous single-task API, but retain the same immutable attempt
        # and error history as batch work. Draft previews still create no saved task/job.
        result = await self.create_prompt_batch(
            project_id,
            task_ids=[task_id],
            target=target,
            include_project_background=context.include_project_background,
            include_previous_task_summary=context.include_previous_task_summary,
            single_input=SinglePromptInput(
                user_prompt, media, duration_seconds, mode, context_mode
            ),
            enqueue=False,
        )
        with self.uow_factory() as uow:
            job = uow.prompt_jobs.list_by_batch(result.batch_id)[0]
        if job.status == JobStatus.FAILED:
            raise ShotMillError(job.error or "PROMPT_INVALID", "请先填写用户提示词。", 422)
        try:
            item = await self._execute_prompt_job(job.id, raise_errors=True)
        finally:
            self.refresh_prompt_batch(result.batch_id)
            await self._publish_batch_event(
                project_id, result.batch_id, task_id=task_id, state="prompt_updated"
            )
        with self.uow_factory() as uow:
            revision = uow.prompt_revisions.get(item.revision_id) if item.revision_id else None
        if revision is None:
            raise ShotMillError("PROMPT_NOT_COMPLETED", "增强尚未完成，请检查运行状态。", 409)
        return revision

    @staticmethod
    def _selected_tasks(tasks: list[Task], task_ids: list[str]) -> list[Task]:
        selected_ids = set(task_ids)
        return sorted(
            (task for task in tasks if not selected_ids or task.id in selected_ids),
            key=lambda task: task.display_order,
        )

    @staticmethod
    def _prompt_text(task: Task, single_input: SinglePromptInput | None = None) -> str:
        return (
            single_input.user_prompt
            if single_input
            else task.user_prompt or task.user_intent or task.summary
        ).strip()

    @classmethod
    def _prompt_skip_reason(
        cls,
        task: Task,
        active_ids: set[str],
        single_input: SinglePromptInput | None = None,
    ) -> PromptBatchSkipped | None:
        if task.id in active_ids:
            return PromptBatchSkipped(task.id, "busy", "正在增强或排队")
        if not cls._prompt_text(task, single_input):
            return PromptBatchSkipped(task.id, "empty-prompt", "缺少用户提示词")
        return None

    def prompt_batch_eligibility(
        self,
        project_id: str,
        task_ids: list[str],
    ) -> PromptBatchEligibility:
        with self.uow_factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            selected = self._selected_tasks(uow.tasks.list_by_project(project_id), task_ids)
            if task_ids and len(selected) != len(set(task_ids)):
                raise NotFoundError("TASK_NOT_FOUND", "One or more tasks were not found")
            active = uow.prompt_jobs.active_task_ids_by_project(project_id)
            eligible: list[str] = []
            skipped: list[PromptBatchSkipped] = []
            for task in selected:
                reason = self._prompt_skip_reason(task, active)
                if reason:
                    skipped.append(reason)
                else:
                    eligible.append(task.id)
            return PromptBatchEligibility(eligible, skipped)

    async def create_prompt_batch(
        self,
        project_id: str,
        *,
        task_ids: list[str],
        include_project_background: bool,
        include_previous_task_summary: bool,
        target: str = "minimax-h3",
        single_input: SinglePromptInput | None = None,
        enqueue: bool = True,
    ) -> BatchPromptResult:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            all_tasks = uow.tasks.list_by_project(project_id)
            selected = self._selected_tasks(all_tasks, task_ids)
            if task_ids and len(selected) != len(set(task_ids)):
                raise NotFoundError("TASK_NOT_FOUND", "One or more tasks were not found")
            active_prompt_task_ids = uow.prompt_jobs.active_task_ids_by_project(project_id)
            if single_input and any(task.id in active_prompt_task_ids for task in selected):
                raise ShotMillError("TASK_PROMPT_BUSY", "任务正在增强，请等待当前增强完成。", 409)
            batch = PromptEnhancementBatch(
                id=new_id("promptbatch"),
                project_id=project_id,
                status="queued",
                total_count=len(selected),
                queued_count=0,
                running_count=0,
            )
            uow.prompt_batches.add(batch)
            previous_by_order = {
                task.id: next(
                    (
                        item
                        for item in reversed(all_tasks)
                        if item.display_order < task.display_order
                    ),
                    None,
                )
                for task in selected
            }
            jobs: list[PromptEnhancementJob] = []
            for task in selected:
                skip = self._prompt_skip_reason(task, active_prompt_task_ids, single_input)
                if skip and skip.reason == "busy":
                    jobs.append(
                        PromptEnhancementJob(
                            id=new_id("promptjob"),
                            batch_id=batch.id,
                            project_id=project_id,
                            task_id=task.id,
                            status=JobStatus.CANCELLED,
                            source_snapshot={},
                            context_snapshot={},
                            provider_profile_snapshot={},
                            target_skill=target,
                            finished_at=utcnow(),
                            error="active-prompt-job",
                        )
                    )
                    continue
                user_prompt = self._prompt_text(task, single_input)
                if skip and skip.reason == "empty-prompt":
                    jobs.append(
                        PromptEnhancementJob(
                            id=new_id("promptjob"),
                            batch_id=batch.id,
                            project_id=project_id,
                            task_id=task.id,
                            status=JobStatus.FAILED,
                            source_snapshot={},
                            context_snapshot={},
                            provider_profile_snapshot={},
                            target_skill=target,
                            finished_at=utcnow(),
                            error="USER_PROMPT_REQUIRED",
                        )
                    )
                    continue
                project_background = None
                if (
                    include_project_background
                    and project.use_description_for_ai_prompt
                    and project.description.strip()
                ):
                    project_background = project.description.strip()
                previous = previous_by_order[task.id]
                previous_summary = None
                if include_previous_task_summary and previous is not None:
                    previous_summary = (
                        previous.summary.strip()
                        or previous.user_intent.strip()
                        or previous.title.strip()
                        or None
                    )
                generation = dict(task.generation_params)
                job = PromptEnhancementJob(
                    id=new_id("promptjob"),
                    batch_id=batch.id,
                    project_id=project_id,
                    task_id=task.id,
                    status=JobStatus.QUEUED,
                    source_snapshot={
                        "userPrompt": user_prompt,
                        "media": [
                            {
                                "assetId": item.asset_id,
                                "reference": item.reference,
                                "role": item.role,
                            }
                            for item in (
                                single_input.media if single_input else task.asset_bindings
                            )
                        ],
                        "durationSeconds": (
                            single_input.duration_seconds
                            if single_input
                            else task.planned_duration_seconds
                        ),
                        "taskRevision": task.revision,
                        "mode": (
                            single_input.mode
                            if single_input
                            else generation.get("mode", "全能参考")
                        ),
                        "contextMode": (
                            single_input.context_mode
                            if single_input
                            else generation.get("contextMode", "不承接")
                        ),
                        "forceAiSource": single_input is None,
                    },
                    context_snapshot={
                        "includeProjectBackground": include_project_background,
                        "includePreviousTaskSummary": include_previous_task_summary,
                        "projectBackground": project_background,
                        "previousTaskSummary": previous_summary,
                    },
                    provider_profile_snapshot=self.prompt_service.capture_provider_profile(),
                    target_skill=target,
                )
                jobs.append(job)
            for job in jobs:
                uow.prompt_jobs.add(job)
            batch.queued_count = sum(job.status == JobStatus.QUEUED for job in jobs)
            batch.failed_count = sum(job.status == JobStatus.FAILED for job in jobs)
            batch.cancelled_count = sum(job.status == JobStatus.CANCELLED for job in jobs)
            uow.prompt_batches.update(batch)

        if enqueue:
            if self.prompt_queue is None:
                raise RuntimeError("Prompt enhancement queue is not attached")
            for job in jobs:
                if job.status == JobStatus.QUEUED:
                    await self.prompt_queue.enqueue(job.id)
        self.refresh_prompt_batch(batch.id)
        await self._publish_batch_event(project_id, batch.id, state="queued")
        return self.prompt_batch_result(project_id, batch.id)

    def prompt_batch_result(self, project_id: str, batch_id: str) -> BatchPromptResult:
        with self.uow_factory() as uow:
            batch = uow.prompt_batches.get(batch_id)
            if batch is None or batch.project_id != project_id:
                raise NotFoundError("PROMPT_BATCH_NOT_FOUND", "Prompt batch not found")
            jobs = uow.prompt_jobs.list_by_batch(batch_id)
        state = {
            "completed_with_errors": "partial",
            "cancelled": "cancelled",
        }.get(batch.status, batch.status)
        items = [
            BatchPromptItemResult(
                task_id=job.task_id,
                state=(
                    "skipped"
                    if job.status == JobStatus.CANCELLED and job.error == "active-prompt-job"
                    else job.status.value
                ),
                revision_id=job.revision_id,
                error=job.error,
            )
            for job in jobs
        ]
        return BatchPromptResult(batch_id=batch.id, state=state, items=items)

    async def cancel_prompt_batch(self, project_id: str, batch_id: str) -> BatchPromptResult:
        # Claim and cancellation both commit before their first await. On this single-process
        # scheduler an executing job cannot be mistaken for a queued job by the cancel action.
        with self.uow_factory() as uow:
            batch = uow.prompt_batches.get(batch_id)
            if batch is None or batch.project_id != project_id:
                raise NotFoundError("PROMPT_BATCH_NOT_FOUND", "Prompt batch not found")
            for job in uow.prompt_jobs.list_by_batch(batch_id):
                if job.status == JobStatus.QUEUED:
                    job.status = JobStatus.CANCELLED
                    job.finished_at = utcnow()
                    uow.prompt_jobs.update(job)
        self.refresh_prompt_batch(batch_id)
        await self._publish_batch_event(project_id, batch_id, state="prompt_cancelled")
        return self.prompt_batch_result(project_id, batch_id)

    async def retry_failed_prompt_batch(self, project_id: str, batch_id: str) -> BatchPromptResult:
        if self.prompt_queue is None:
            raise RuntimeError("Prompt enhancement queue is not attached")
        with self.uow_factory() as uow:
            previous = uow.prompt_batches.get(batch_id)
            if previous is None or previous.project_id != project_id:
                raise NotFoundError("PROMPT_BATCH_NOT_FOUND", "Prompt batch not found")
            active_ids = uow.prompt_jobs.active_task_ids_by_project(project_id)
            failed = [
                job
                for job in uow.prompt_jobs.list_by_batch(batch_id)
                if job.status == JobStatus.FAILED and job.task_id not in active_ids
            ]
            if not failed:
                raise ShotMillError(
                    "NO_RETRYABLE_PROMPT_JOBS", "没有可重试的失败任务，或任务已在增强中。", 409
                )
            batch = PromptEnhancementBatch(
                id=new_id("promptbatch"),
                project_id=project_id,
                status="queued",
                total_count=len(failed),
                queued_count=len(failed),
            )
            uow.prompt_batches.add(batch)
            attempts = [
                PromptEnhancementJob(
                    id=new_id("promptjob"),
                    batch_id=batch.id,
                    project_id=project_id,
                    task_id=job.task_id,
                    status=JobStatus.QUEUED,
                    source_snapshot=deepcopy(job.source_snapshot),
                    context_snapshot=deepcopy(job.context_snapshot),
                    provider_profile_snapshot=deepcopy(job.provider_profile_snapshot),
                    target_skill=job.target_skill,
                )
                for job in failed
            ]
            for job in attempts:
                uow.prompt_jobs.add(job)
        for job in attempts:
            await self.prompt_queue.enqueue(job.id)
        await self._publish_batch_event(project_id, batch.id, state="queued")
        return self.prompt_batch_result(project_id, batch.id)

    def refresh_prompt_batch(self, batch_id: str) -> PromptEnhancementBatch | None:
        with self.uow_factory() as uow:
            batch = uow.prompt_batches.get(batch_id)
            if batch is None:
                return None
            jobs = uow.prompt_jobs.list_by_batch(batch_id)
            counts = {status: sum(job.status == status for job in jobs) for status in JobStatus}
            batch.queued_count = counts[JobStatus.QUEUED]
            batch.running_count = counts[JobStatus.RUNNING]
            batch.completed_count = counts[JobStatus.COMPLETED]
            batch.failed_count = counts[JobStatus.FAILED]
            batch.cancelled_count = counts[JobStatus.CANCELLED]
            if batch.running_count:
                batch.status = "running"
                batch.started_at = batch.started_at or utcnow()
                batch.finished_at = None
            elif batch.queued_count:
                batch.status = "queued"
                batch.finished_at = None
            elif batch.cancelled_count == batch.total_count and batch.total_count:
                batch.status = "cancelled"
                batch.finished_at = batch.finished_at or utcnow()
            elif batch.failed_count or batch.cancelled_count:
                batch.status = "completed_with_errors" if batch.completed_count else "failed"
                batch.finished_at = batch.finished_at or utcnow()
            else:
                batch.status = "completed"
                batch.finished_at = batch.finished_at or utcnow()
            uow.prompt_batches.update(batch)
            return batch

    async def _publish_batch_event(
        self,
        project_id: str,
        batch_id: str,
        *,
        task_id: str | None = None,
        state: str,
    ) -> None:
        if self.events is None:
            return
        await self.events.publish(
            project_id,
            "project.runtime_changed",
            taskId=task_id,
            batchId=batch_id,
            state=state,
        )
        await self.events.publish(project_id, "project.summary_changed", batchId=batch_id)

    async def _execute_prompt_job(
        self, job_id: str, *, raise_errors: bool = False
    ) -> BatchPromptItemResult:
        with self.uow_factory() as uow:
            job = uow.prompt_jobs.get(job_id)
            if job is None:
                raise NotFoundError("PROMPT_JOB_NOT_FOUND", "Prompt job not found")
            if job.status != JobStatus.QUEUED or uow.runtime_controls.get(job_id).paused:
                return BatchPromptItemResult(
                    task_id=job.task_id,
                    state="skipped",
                    error="prompt-job-not-queued",
                )
            job.status = JobStatus.RUNNING
            job.started_at = utcnow()
            uow.prompt_jobs.update(job)
            task = uow.tasks.get(job.task_id)
            if task is not None and task.id not in uow.jobs.active_task_ids_by_project(
                job.project_id
            ):
                task.state = TaskState.PROMPT_GENERATING
                task.progress = 0.0
                task.updated_at = utcnow()
                uow.tasks.update(task)
        await self._publish_batch_event(
            job.project_id,
            job.batch_id,
            task_id=job.task_id,
            state="prompt_running",
        )

        try:
            media = tuple(
                EnhancementMedia(
                    asset_id=item["assetId"],
                    reference=item["reference"],
                    role=item.get("role"),
                )
                for item in job.source_snapshot.get("media", [])
            )
            revision = await self.prompt_service.enhance_from_snapshot(
                job.project_id,
                job.task_id,
                target=job.target_skill,
                user_prompt=str(job.source_snapshot.get("userPrompt", "")),
                media=media,
                include_project_background=bool(
                    job.context_snapshot.get("includeProjectBackground")
                ),
                include_previous_task_summary=bool(
                    job.context_snapshot.get("includePreviousTaskSummary")
                ),
                project_background_snapshot=job.context_snapshot.get("projectBackground"),
                previous_task_summary_snapshot=job.context_snapshot.get("previousTaskSummary"),
                duration_seconds=float(job.source_snapshot.get("durationSeconds", 6)),
                mode=str(job.source_snapshot.get("mode", "全能参考")),
                context_mode=job.source_snapshot.get("contextMode"),
                expected_task_revision=(
                    int(job.source_snapshot["taskRevision"])
                    if job.source_snapshot.get("taskRevision") is not None
                    else None
                ),
                provider_profile_snapshot=job.provider_profile_snapshot,
                force_ai_source=bool(job.source_snapshot.get("forceAiSource", True)),
            )
            with self.uow_factory() as uow:
                current = uow.prompt_jobs.get(job_id)
                if current is not None:
                    current.status = JobStatus.COMPLETED
                    current.finished_at = utcnow()
                    current.revision_id = revision.id
                    uow.prompt_jobs.update(current)
            await self._publish_batch_event(
                job.project_id,
                job.batch_id,
                task_id=job.task_id,
                state="prompt_completed",
            )
            return BatchPromptItemResult(
                task_id=job.task_id,
                state="completed",
                revision_id=revision.id,
            )
        except Exception as exc:
            with self.uow_factory() as uow:
                current = uow.prompt_jobs.get(job_id)
                if current is not None:
                    current.status = JobStatus.FAILED
                    current.finished_at = utcnow()
                    current.error = getattr(exc, "code", str(exc))
                    uow.prompt_jobs.update(current)
                task = uow.tasks.get(job.task_id)
                expected_revision = job.source_snapshot.get("taskRevision")
                if (
                    task is not None
                    and (expected_revision is None or task.revision == int(expected_revision))
                    and task.id not in uow.jobs.active_task_ids_by_project(job.project_id)
                ):
                    task.state = TaskState.FAILED
                    task.progress = None
                    task.updated_at = utcnow()
                    uow.tasks.update(task)
            await self._publish_batch_event(
                job.project_id,
                job.batch_id,
                task_id=job.task_id,
                state="prompt_failed",
            )
            if raise_errors:
                raise
            return BatchPromptItemResult(
                task_id=job.task_id,
                state="failed",
                error=getattr(exc, "code", str(exc)),
            )

    async def video_batch_eligibility(
        self, project_id: str, task_ids: list[str]
    ) -> VideoBatchEligibility:
        with self.uow_factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = self._selected_tasks(uow.tasks.list_by_project(project_id), task_ids)
            if task_ids and len(tasks) != len(set(task_ids)):
                raise NotFoundError("TASK_NOT_FOUND", "One or more tasks were not found")
            active_video_task_ids = uow.jobs.active_task_ids_by_project(project_id)
            eligible: list[str] = []
            skipped: list[VideoBatchSkipped] = []
            for task in tasks:
                if task.id in active_video_task_ids or task.state in {
                    TaskState.QUEUED,
                    TaskState.RUNNING,
                }:
                    skipped.append(VideoBatchSkipped(task.id, "busy"))
                    continue
                if not task.final_prompt.strip():
                    skipped.append(VideoBatchSkipped(task.id, "invalid-params"))
                    continue
                eligible.append(task.id)
        with self.uow_factory() as uow:
            ordered = uow.tasks.list_by_project(project_id)
        previous = {task.id: ordered[index - 1].id for index, task in enumerate(ordered) if index}
        modes = {task.id: task.generation_params.get("contextMode") for task in ordered}
        validated: list[str] = []
        warnings = []
        for task_id in eligible:
            try:
                preview = await self.generation_service.validate_task(
                    project_id,
                    task_id,
                    dependency={"sourceTaskId": previous[task_id], "sourceJobId": "preflight"}
                    if modes[task_id] == "尾帧承接" and previous.get(task_id) in validated
                    else None,
                )
                warnings.extend(
                    {
                        "taskId": task_id,
                        "title": preview.task_content_snapshot["title"],
                        "message": message,
                    }
                    for message in preview.context_snapshot.get("warnings", [])
                )
                validated.append(task_id)
            except ShotMillError as exc:
                skipped.append(self._video_skipped(task_id, exc))
        return VideoBatchEligibility(
            eligible_task_ids=validated,
            skipped=skipped,
            warnings=warnings,
        )

    @staticmethod
    def _video_skipped(task_id: str, error: ShotMillError) -> VideoBatchSkipped:
        reason = {
            "TASK_BUSY": "busy",
        }.get(error.code, "invalid-params")
        return VideoBatchSkipped(task_id, reason, error.code, error.message)

    async def create_video_batch(self, project_id: str, task_ids: list[str]) -> VideoBatchResult:
        eligibility = await self.video_batch_eligibility(project_id, task_ids)
        batch_id = new_id("videobatch")
        submitted_task_ids: list[str] = []
        skipped = list(eligibility.skipped)
        with self.uow_factory() as uow:
            ordered = uow.tasks.list_by_project(project_id)
        previous = {task.id: ordered[index - 1].id for index, task in enumerate(ordered) if index}
        modes = {task.id: task.generation_params.get("contextMode") for task in ordered}
        submitted_jobs = {}
        for task_id in eligibility.eligible_task_ids:
            try:
                source_job = submitted_jobs.get(previous.get(task_id))
                if (
                    modes[task_id] == "尾帧承接"
                    and previous.get(task_id) in eligibility.eligible_task_ids
                    and source_job is None
                ):
                    raise ShotMillError(
                        "CONTEXT_DEPENDENCY_NOT_SUBMITTED",
                        "上一任务未能进入本批队列，请重新检查后提交。",
                        409,
                    )
                job = await self.generation_service.submit(
                    project_id,
                    task_id,
                    dependency={"sourceTaskId": source_job.task_id, "sourceJobId": source_job.id}
                    if source_job and modes[task_id] == "尾帧承接"
                    else None,
                )
                submitted_jobs[task_id] = job
                submitted_task_ids.append(task_id)
            except ShotMillError as exc:
                # Eligibility is calculated just before submission. If a task becomes invalid
                # between the read and submit, leave later tasks free to continue.
                skipped.append(self._video_skipped(task_id, exc))
                continue
            await asyncio.sleep(0)
        return VideoBatchResult(
            batch_id=batch_id,
            eligible_task_ids=submitted_task_ids,
            skipped=skipped,
            warnings=eligibility.warnings,
        )


class PromptEnhancementQueue:
    def __init__(self, service: BatchProductionService, workers: int = 1) -> None:
        self.service = service
        self.workers = max(1, workers)
        self._queue: asyncio.Queue[str | None] = ManagedQueue(service.uow_factory)
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        with self.service.uow_factory() as uow:
            jobs = uow.prompt_jobs.list_active()
            for job in jobs:
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.QUEUED
                    job.started_at = None
                    uow.prompt_jobs.update(job)
        self._started = True
        self._tasks = [
            asyncio.create_task(self._worker(), name=f"shotmill-prompt-{index}")
            for index in range(self.workers)
        ]
        for job in jobs:
            await self._queue.put(job.id)

    async def stop(self) -> None:
        if not self._started:
            return
        for _ in self._tasks:
            await self._queue.put(None)
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False

    async def enqueue(self, job_id: str) -> None:
        if not self._started:
            await self.start()
        await self._queue.put(job_id)

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if job_id is None:
                    return
                result = await self.service._execute_prompt_job(job_id)
                with self.service.uow_factory() as uow:
                    job = uow.prompt_jobs.get(job_id)
                if job is not None:
                    self.service.refresh_prompt_batch(job.batch_id)
                    await self.service._publish_batch_event(
                        job.project_id,
                        job.batch_id,
                        task_id=job.task_id,
                        state=f"prompt_{result.state}",
                    )
            finally:
                self._queue.task_done()
