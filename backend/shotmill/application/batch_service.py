from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationService
from shotmill.application.prompt_enhancement_service import (
    EnhancementMedia,
    PromptEnhancementService,
)
from shotmill.application.prompt_review import prompt_hash, prompt_review_status
from shotmill.domain.entities import (
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


@dataclass(frozen=True, slots=True)
class VideoBatchEligibility:
    eligible_task_ids: list[str]
    skipped: list[VideoBatchSkipped]


@dataclass(frozen=True, slots=True)
class VideoBatchResult(VideoBatchEligibility):
    batch_id: str


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

    @staticmethod
    def _selected_tasks(tasks: list[Task], task_ids: list[str]) -> list[Task]:
        if not task_ids:
            return tasks
        order = {task_id: index for index, task_id in enumerate(task_ids)}
        selected = [task for task in tasks if task.id in order]
        selected.sort(key=lambda task: order[task.id])
        return selected

    async def create_prompt_batch(
        self,
        project_id: str,
        *,
        task_ids: list[str],
        include_project_background: bool,
        include_previous_task_summary: bool,
        target: str = "minimax-h3",
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
                if task.id in active_prompt_task_ids:
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
                user_prompt = (task.user_prompt or task.user_intent or task.summary).strip()
                if not user_prompt:
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
                            for item in task.asset_bindings
                        ],
                        "durationSeconds": task.planned_duration_seconds,
                        "taskRevision": task.revision,
                        "mode": generation.get("mode", "全能参考"),
                        "contextMode": generation.get("contextMode", "不承接"),
                    },
                    context_snapshot={
                        "includeProjectBackground": include_project_background,
                        "includePreviousTaskSummary": include_previous_task_summary,
                        "projectBackground": project_background,
                        "previousTaskSummary": previous_summary,
                    },
                    provider_profile_snapshot={
                        "providerId": self.prompt_service.provider.id,
                        "modelId": None,
                    },
                    target_skill=target,
                )
                jobs.append(job)
            for job in jobs:
                uow.prompt_jobs.add(job)
            batch.queued_count = sum(job.status == JobStatus.QUEUED for job in jobs)
            batch.failed_count = sum(job.status == JobStatus.FAILED for job in jobs)
            batch.cancelled_count = sum(job.status == JobStatus.CANCELLED for job in jobs)
            uow.prompt_batches.update(batch)

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
                state="skipped" if job.status == JobStatus.CANCELLED else job.status.value,
                revision_id=job.revision_id,
                error=job.error,
            )
            for job in jobs
        ]
        return BatchPromptResult(batch_id=batch.id, state=state, items=items)

    def refresh_prompt_batch(self, batch_id: str) -> PromptEnhancementBatch | None:
        with self.uow_factory() as uow:
            batch = uow.prompt_batches.get(batch_id)
            if batch is None:
                return None
            jobs = uow.prompt_jobs.list_by_batch(batch_id)
            counts = {
                status: sum(job.status == status for job in jobs)
                for status in JobStatus
            }
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
                batch.finished_at = utcnow()
            elif batch.failed_count:
                batch.status = "completed_with_errors" if batch.completed_count else "failed"
                batch.finished_at = utcnow()
            else:
                batch.status = "completed"
                batch.finished_at = utcnow()
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

    async def _execute_prompt_job(self, job_id: str) -> BatchPromptItemResult:
        with self.uow_factory() as uow:
            job = uow.prompt_jobs.get(job_id)
            if job is None:
                raise NotFoundError("PROMPT_JOB_NOT_FOUND", "Prompt job not found")
            if job.status != JobStatus.QUEUED:
                return BatchPromptItemResult(
                    task_id=job.task_id,
                    state="skipped",
                    error="prompt-job-not-queued",
                )
            job.status = JobStatus.RUNNING
            job.started_at = utcnow()
            uow.prompt_jobs.update(job)
            task = uow.tasks.get(job.task_id)
            if task is not None:
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
                if task is not None and (
                    expected_revision is None or task.revision == int(expected_revision)
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
            return BatchPromptItemResult(
                task_id=job.task_id,
                state="failed",
                error=getattr(exc, "code", str(exc)),
            )

    def video_batch_eligibility(
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
                if prompt_review_status(task) != "approved":
                    skipped.append(VideoBatchSkipped(task.id, "not-reviewed"))
                    continue
                if (
                    task.approved_prompt_hash
                    != prompt_hash(task.prompt_source, task.final_prompt.strip())
                ):
                    skipped.append(VideoBatchSkipped(task.id, "not-reviewed"))
                    continue
                eligible.append(task.id)
            return VideoBatchEligibility(eligible_task_ids=eligible, skipped=skipped)

    async def create_video_batch(self, project_id: str, task_ids: list[str]) -> VideoBatchResult:
        eligibility = self.video_batch_eligibility(project_id, task_ids)
        batch_id = new_id("videobatch")
        submitted_task_ids: list[str] = []
        skipped = list(eligibility.skipped)
        for task_id in eligibility.eligible_task_ids:
            try:
                await self.generation_service.submit(project_id, task_id)
                submitted_task_ids.append(task_id)
            except ShotMillError as exc:
                # Eligibility is calculated just before submission. If a task becomes invalid
                # between the read and submit, leave later tasks free to continue.
                reason = "busy" if getattr(exc, "code", "") == "TASK_BUSY" else "invalid-params"
                skipped.append(VideoBatchSkipped(task_id, reason))
                continue
            await asyncio.sleep(0)
        return VideoBatchResult(
            batch_id=batch_id,
            eligible_task_ids=submitted_task_ids,
            skipped=skipped,
        )


class PromptEnhancementQueue:
    def __init__(self, service: BatchProductionService, workers: int = 1) -> None:
        self.service = service
        self.workers = max(1, workers)
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
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
