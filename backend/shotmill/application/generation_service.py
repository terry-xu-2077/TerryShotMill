from __future__ import annotations

import asyncio
import math
import mimetypes
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict

from shotmill.application.continuation_risks import MISSING_PREVIOUS_VIDEO
from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.managed_queue import ManagedQueue
from shotmill.domain.entities import ContextLink, Job, Result, new_id, utcnow
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.domain.providers import (
    ResolvedMedia,
    ResumableVideoGenerationProvider,
    SnapshotVideoGenerationProvider,
    ValidatingVideoGenerationProvider,
    VideoGenerationProvider,
    VideoGenerationRequest,
)
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.media.context import file_digest, prepare_context_media
from shotmill.media.previews import result_with_preview
from shotmill.media.storage import MediaStorage


class GenerationService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        provider: VideoGenerationProvider,
        storage: MediaStorage,
        events: ProjectEventBus,
    ) -> None:
        self.uow_factory = uow_factory
        self.provider = provider
        self.storage = storage
        self.events = events
        self.queue: GenerationQueue | None = None
        self._executing: set[str] = set()

    def attach_queue(self, queue: GenerationQueue) -> None:
        self.queue = queue

    def get_job(self, job_id: str) -> Job:
        with self.uow_factory() as uow:
            job = uow.jobs.get(job_id)
            if job is None:
                raise NotFoundError("JOB_NOT_FOUND", "Job not found")
            return job

    async def cancel_queued(self, project_id: str, job_ids: list[str]) -> list[str]:
        # Queue claims and cancellation commit before yielding in the local scheduler.
        # Only the explicitly displayed jobs are candidates; newly submitted work is untouched.
        cancelled: list[str] = []
        with self.uow_factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            jobs = [uow.jobs.get(job_id) for job_id in dict.fromkeys(job_ids)]
            if any(job is None or job.project_id != project_id for job in jobs):
                raise NotFoundError("JOB_NOT_FOUND", "Video job not found")
            task_ids: set[str] = set()
            for job in jobs:
                if job.status != JobStatus.QUEUED:
                    continue
                job.status = JobStatus.CANCELLED
                job.completed_at = utcnow()
                uow.jobs.update_runtime(job)
                cancelled.append(job.id)
                task_ids.add(job.task_id)
            active_video = uow.jobs.active_task_ids_by_project(project_id)
            active_prompt = uow.prompt_jobs.active_task_ids_by_project(project_id)
            for task_id in task_ids - active_video:
                task = uow.tasks.get(task_id)
                if task is None:
                    continue
                task.state = (
                    TaskState.PROMPT_GENERATING
                    if task_id in active_prompt
                    else TaskState.COMPLETED
                    if task.primary_result_id
                    else TaskState.PROMPT_READY
                    if task.final_prompt.strip()
                    else TaskState.DRAFT
                )
                task.progress = 100.0 if task.state == TaskState.COMPLETED else None
                task.updated_at = utcnow()
                uow.tasks.update(task)
        for job_id in cancelled:
            await self.wake_dependents(job_id)
        if cancelled:
            await self.events.publish(project_id, "project.runtime_changed")
            await self.events.publish(project_id, "project.summary_changed")
        return cancelled

    async def validate_task(
        self,
        project_id: str,
        task_id: str,
        *,
        seed: int | None = None,
        dependency: dict | None = None,
    ) -> Job:
        """Build the exact execution input without saving or scheduling a Job."""
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            if task.state in {
                TaskState.QUEUED,
                TaskState.RUNNING,
            } or task_id in uow.jobs.active_task_ids_by_project(project_id):
                raise ConflictError("TASK_BUSY", "Task is already queued or running")
            if not task.final_prompt.strip():
                raise ShotMillError("TASK_PROMPT_REQUIRED", "Task has no final prompt", 422)

            assets_snapshot: list[dict] = []
            for binding in task.asset_bindings:
                asset = uow.assets.get(binding.asset_id)
                if asset is None or asset.project_id != project_id:
                    raise NotFoundError("ASSET_NOT_FOUND", f"Asset not found: {binding.asset_id}")
                assets_snapshot.append(
                    {
                        "assetId": asset.id,
                        "reference": binding.reference,
                        "role": binding.role,
                        "mediaType": asset.media_type,
                        "projectRelativePath": asset.project_relative_path,
                        "originalFilename": asset.original_filename,
                    }
                )
            context_links = uow.contexts.list_by_target(task.id)
            context_sources = []
            mode = task.generation_params.get("contextMode", "不承接")
            warnings = []
            if dependency:
                previous = next(
                    (
                        item
                        for item in reversed(uow.tasks.list_by_project(project_id))
                        if item.display_order < task.display_order
                    ),
                    None,
                )
                if (
                    mode != "尾帧承接"
                    or previous is None
                    or previous.id != dependency["sourceTaskId"]
                    or any(
                        link.project_id != project_id or link.source_task_id != previous.id
                        for link in context_links
                    )
                ):
                    raise ShotMillError(
                        "CONTEXT_DEPENDENCY_INVALID", "批量承接关系已变化，请重新提交。", 409
                    )
                # The submitted source Job is immutable; its Result does not exist yet.
                context_links = []
            if (
                not dependency
                and mode == "尾帧承接"
                and (
                    not context_links
                    or (len(context_links) == 1 and not context_links[0].source_result_id)
                )
            ):
                previous = next(
                    (
                        item
                        for item in reversed(uow.tasks.list_by_project(project_id))
                        if item.display_order < task.display_order
                    ),
                    None,
                )
                if previous and previous.primary_result_id:
                    context_links = [
                        ContextLink(
                            new_id("context"),
                            project_id,
                            previous.id,
                            task.id,
                            "visual",
                            previous.primary_result_id,
                        )
                    ]
                else:
                    if previous:
                        warnings.append(MISSING_PREVIOUS_VIDEO)
                    mode = "不承接"
                    context_links = []
            if not dependency and mode in {"片段承接", "尾帧承接"}:
                if len(context_links) != 1 or not context_links[0].source_result_id:
                    raise ShotMillError(
                        "CONTEXT_RESULT_REQUIRED", "请先生成上一任务的视频并重新保存承接设置。", 409
                    )
                link = context_links[0]
                source = uow.tasks.get(link.source_task_id)
                result = uow.results.get(link.source_result_id)
                if (
                    source is None
                    or result is None
                    or source.project_id != project_id
                    or result.project_id != project_id
                    or result.task_id != source.id
                    or link.project_id != project_id
                ):
                    raise ShotMillError("CONTEXT_RESULT_REQUIRED", "上下文来源结果无效。", 409)
                if link.stale or source.primary_result_id != result.id:
                    raise ShotMillError(
                        "CONTEXT_STALE", "上一任务结果已变化，请重新确认并保存承接设置。", 409
                    )
                prefix = f"/media/{project_id}/"
                if not result.video_url.startswith(prefix):
                    raise ShotMillError(
                        "CONTEXT_MEDIA_INVALID", "上下文来源必须是本项目已保存的视频。", 422
                    )
                context_sources.append((source.id, result.id, result.video_url[len(prefix) :]))
            job = Job(
                id=new_id("job"),
                project_id=project_id,
                task_id=task.id,
                status=JobStatus.QUEUED,
                final_prompt_snapshot=task.final_prompt,
                task_content_snapshot={
                    "title": task.title,
                    "summary": task.summary,
                    "userIntent": task.user_intent,
                    "plannedDurationSeconds": task.planned_duration_seconds,
                    "promptSource": task.prompt_source.value,
                    "taskRevision": task.revision,
                },
                assets_snapshot=assets_snapshot,
                generation_profile_snapshot={
                    "profileId": task.generation_params.get("profileId", "default"),
                    "target": task.generation_params.get("target", "minimax-h3"),
                },
                provider_profile_snapshot={
                    "providerId": self.provider.id,
                    "capability": asdict(self.provider.capability),
                },
                params_snapshot={**deepcopy(task.generation_params), "contextMode": mode},
                context_snapshot={
                    "links": [
                        {
                            "id": link.id,
                            "sourceTaskId": link.source_task_id,
                            "kind": link.kind,
                            "sourceResultId": link.source_result_id,
                            "stale": link.stale,
                        }
                        for link in context_links
                    ]
                },
                seed=seed,
            )
        if dependency:
            job.context_snapshot["dependency"] = deepcopy(dependency)
        job.context_snapshot["media"] = []
        if warnings:
            job.context_snapshot["warnings"] = warnings
            job.context_snapshot["requestedMode"] = task.generation_params.get("contextMode")
        for source_id, result_id, path in context_sources:
            media = await asyncio.to_thread(
                prepare_context_media,
                self.storage,
                project_id,
                result_id,
                path,
                mode,
                job.params_snapshot.get("contextStartSeconds"),
                job.params_snapshot.get("contextEndSeconds"),
            )
            kind = "Video" if media["mediaType"] == "video" else "Picture"
            used = {item["reference"] for item in assets_snapshot}
            index = 1
            while f"<{kind} {index}>" in used or f"<{kind} {index}>" in job.final_prompt_snapshot:
                index += 1
            media.update(sourceTaskId=source_id, reference=f"<{kind} {index}>")
            job.context_snapshot["media"].append(media)
        request = self._provider_request(job, preflight=True)
        if isinstance(self.provider, SnapshotVideoGenerationProvider):
            job.provider_profile_snapshot.update(deepcopy(self.provider.capture_profile(request)))
        provider = self._execution_provider(job)
        self._validate_capability(request, provider)
        if isinstance(provider, ValidatingVideoGenerationProvider):
            validated_profile = await provider.validate(request)
            if validated_profile is not None:
                job.provider_profile_snapshot.update(deepcopy(validated_profile))
        return job

    def _execution_provider(self, job: Job) -> VideoGenerationProvider:
        profile = job.provider_profile_snapshot
        if profile.get("providerId") != self.provider.id:
            raise ShotMillError("VIDEO_PROVIDER_CHANGED", "原视频生成服务不可用，请重新提交。", 409)
        if isinstance(self.provider, SnapshotVideoGenerationProvider):
            return self.provider.bind_profile(deepcopy(profile))
        return self.provider

    def _provider_request(self, job: Job, *, preflight: bool = False) -> VideoGenerationRequest:
        resolved: list[ResolvedMedia] = []
        context = job.execution_context or job.context_snapshot
        context_media = context.get("media", [])
        pending = preflight and "dependency" in context

        if (
            job.params_snapshot.get("contextMode") in {"片段承接", "尾帧承接"}
            and not context_media
            and not pending
            and not job.execution_context
        ):
            raise ShotMillError(
                "CONTEXT_SNAPSHOT_MISSING", "旧任务缺少上下文媒体快照，请重新提交。", 409
            )
        for snapshot in [*job.assets_snapshot, *context_media]:
            path = self.storage.resolve(job.project_id, snapshot["projectRelativePath"])
            if snapshot in context_media and (
                not path.is_file() or file_digest(path) != snapshot["sha256"]
            ):
                raise ShotMillError(
                    "CONTEXT_MEDIA_CHANGED", "上下文媒体缺失或已变化，请重新提交。", 409
                )
            if not path.is_file():
                raise ShotMillError(
                    "GENERATION_ASSET_FILE_MISSING", "引用的素材文件不存在，请重新导入素材。", 409
                )
            mime, _ = mimetypes.guess_type(snapshot.get("originalFilename", ""))
            resolved.append(
                ResolvedMedia(
                    asset_id=snapshot["assetId"],
                    reference=snapshot["reference"],
                    role=snapshot.get("role"),
                    media_type=snapshot["mediaType"],
                    path=path,
                    mime_type=mime,
                )
            )
        params = deepcopy(job.params_snapshot)
        if job.execution_context:
            params["contextMode"] = job.execution_context["mode"]
        elif pending:
            params["contextMode"] = "不承接"
        params["durationSeconds"] = job.task_content_snapshot.get("plannedDurationSeconds", 6)
        return VideoGenerationRequest(
            job_id=job.id,
            project_id=job.project_id,
            task_id=job.task_id,
            final_prompt=job.final_prompt_snapshot,
            assets=tuple(resolved),
            params=params,
            seed=job.seed,
        )

    def _validate_capability(
        self,
        request: VideoGenerationRequest,
        provider: VideoGenerationProvider,
    ) -> None:
        capability = provider.capability
        duration = request.params["durationSeconds"]
        if not math.isfinite(duration) or duration <= 0:
            raise ShotMillError("GENERATION_DURATION_INVALID", "生成时长必须为正数。", 422)
        if capability.max_duration_seconds and duration > capability.max_duration_seconds:
            raise ShotMillError(
                "GENERATION_DURATION_UNSUPPORTED",
                f"当前生成服务最多支持 {capability.max_duration_seconds:g} 秒。",
                422,
            )
        for media in request.assets:
            if (media.media_type == "image" and not capability.image) or (
                media.media_type == "video" and not capability.reference_videos
            ):
                raise ShotMillError(
                    "GENERATION_MEDIA_UNSUPPORTED", "当前生成服务不支持所选素材类型。", 422
                )

    async def submit(
        self,
        project_id: str,
        task_id: str,
        *,
        seed: int | None = None,
        dependency: dict | None = None,
    ) -> Job:
        job = await self.validate_task(project_id, task_id, seed=seed, dependency=dependency)
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            if task_id in uow.jobs.active_task_ids_by_project(project_id):
                raise ConflictError("TASK_BUSY", "任务已在视频队列中。")
            if task.revision != job.task_content_snapshot["taskRevision"]:
                raise ConflictError("TASK_REVISION_CONFLICT", "任务已变化，请重新检查生成条件。")
            for media in job.context_snapshot.get("media", []):
                source = uow.tasks.get(media["sourceTaskId"])
                if source is None or source.primary_result_id != media["sourceResultId"]:
                    raise ConflictError("CONTEXT_STALE", "检查期间上一任务结果已变化，请重新提交。")
            uow.jobs.add(job)
            task.state = TaskState.QUEUED
            task.progress = 0.0
            task.updated_at = utcnow()
            uow.tasks.update(task)

        await self.events.publish(
            project_id,
            "task.status_changed",
            taskId=task_id,
            status="queued",
            progress=0,
        )
        await self.events.publish(
            project_id, "project.runtime_changed", taskId=task_id, state="queued"
        )
        if self.queue is None:
            raise RuntimeError("Generation queue is not attached")
        await self.queue.enqueue(job.id)
        return job

    async def wake_dependents(self, source_job_id: str) -> None:
        if self.queue is None:
            return
        with self.uow_factory() as uow:
            ids = [
                job.id
                for job in uow.jobs.list_active()
                if job.status == JobStatus.QUEUED
                and job.context_snapshot.get("dependency", {}).get("sourceJobId") == source_job_id
                and not uow.runtime_controls.get(job.id).paused
            ]
        for job_id in ids:
            await self.queue.enqueue(job_id)

    async def resolve_dependency(self, job: Job) -> bool:
        dependency = job.context_snapshot.get("dependency")
        if not dependency or job.execution_context is not None:
            return True
        with self.uow_factory() as uow:
            source = uow.jobs.get(dependency["sourceJobId"])
            if source and (
                source.project_id != job.project_id or source.task_id != dependency["sourceTaskId"]
            ):
                raise ShotMillError("CONTEXT_DEPENDENCY_INVALID", "承接来源不属于本次任务。", 409)
            if source and source.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                return False
            results = (
                [
                    result
                    for result in uow.results.list_by_task(source.task_id)
                    if result.job_id == source.id and result.project_id == job.project_id
                ]
                if source and source.status == JobStatus.COMPLETED
                else []
            )
        warning = "上一任务本次未能提供可用视频；继续生成将不使用尾帧承接，可能出现画面不连续。"
        context = None
        if job.error_code != "CONTEXT_DEPENDENCY_UNAVAILABLE" and results:
            result = min(results, key=lambda item: (item.created_at, item.id))
            prefix = f"/media/{job.project_id}/"
            try:
                if not result.video_url.startswith(prefix):
                    raise ValueError("Non-local context result")
                media = await asyncio.to_thread(
                    prepare_context_media,
                    self.storage,
                    job.project_id,
                    result.id,
                    result.video_url[len(prefix) :],
                    "尾帧承接",
                    None,
                    None,
                )
                used = {item["reference"] for item in job.assets_snapshot}
                index = 1
                while (
                    f"<Picture {index}>" in used
                    or f"<Picture {index}>" in job.final_prompt_snapshot
                ):
                    index += 1
                media.update(sourceTaskId=source.task_id, reference=f"<Picture {index}>")
                context = {"mode": "尾帧承接", "media": [media], "sourceJobId": source.id}
            except (ShotMillError, ValueError, OSError) as exc:
                warning = (
                    f"上一任务尾帧无法读取；继续生成将不使用尾帧承接，可能出现画面不连续。{exc}"
                )
        with self.uow_factory() as uow:
            current = uow.jobs.get(job.id)
            control = uow.runtime_controls.get(job.id)
            if current is None or current.status != JobStatus.QUEUED or control.paused:
                return False
            if context is None:
                if current.error_code != "CONTEXT_DEPENDENCY_UNAVAILABLE":
                    current.error_code = "CONTEXT_DEPENDENCY_UNAVAILABLE"
                    current.error_message = warning + " 可在运行中心选择“继续生成（不承接）”。"
                    uow.jobs.update_runtime(current)
                    control.paused = True
                    uow.runtime_controls.save(control)
                else:
                    context = {
                        "mode": "不承接",
                        "media": [],
                        "warnings": [current.error_message],
                        "sourceJobId": dependency["sourceJobId"],
                    }
            if context is not None:
                uow.jobs.bind_execution_context(job.id, context)
        await self.events.publish(job.project_id, "project.runtime_changed")
        await self.events.publish(job.project_id, "project.summary_changed")
        return context is not None

    async def execute(self, job_id: str, *, recover: bool = False) -> None:
        # One local scheduler process owns execution. Duplicate queue deliveries are harmless.
        if job_id in self._executing:
            return
        self._executing.add(job_id)
        try:
            await self._execute(job_id, recover=recover)
        finally:
            self._executing.discard(job_id)
            with self.uow_factory() as uow:
                job = uow.jobs.get(job_id)
            if job and job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                await self.wake_dependents(job_id)

    async def _execute(self, job_id: str, *, recover: bool) -> None:
        project_id: str | None = None
        task_id: str | None = None
        try:
            with self.uow_factory() as uow:
                pending_job = uow.jobs.get(job_id)
                if pending_job is None:
                    return
                project_id, task_id = pending_job.project_id, pending_job.task_id
                if (
                    pending_job.status == JobStatus.QUEUED
                    and uow.runtime_controls.get(job_id).paused
                ):
                    return
            if pending_job.status == JobStatus.QUEUED and not await self.resolve_dependency(
                pending_job
            ):
                return
            with self.uow_factory() as uow:
                job = uow.jobs.get(job_id)
                if job is None:
                    return
                if uow.runtime_controls.get(job_id).paused:
                    return
                resuming = recover and job.status == JobStatus.RUNNING
                if job.status != JobStatus.QUEUED and not resuming:
                    return
                project_id = job.project_id
                task_id = job.task_id
                task = uow.tasks.get(job.task_id)
                if task is None:
                    raise NotFoundError("TASK_NOT_FOUND", "Task not found")
                job.status = JobStatus.RUNNING
                job.started_at = job.started_at or utcnow()
                uow.jobs.update_runtime(job)
                task.state = TaskState.RUNNING
                task.progress = 0.0
                task.updated_at = utcnow()
                uow.tasks.update(task)

            await self.events.publish(
                project_id,
                "task.status_changed",
                taskId=task_id,
                status="running",
                progress=0,
            )
            await self.events.publish(
                project_id, "project.runtime_changed", taskId=task_id, state="running"
            )

            provider = self._execution_provider(job)
            if resuming:
                if not provider.capability.job_resumption or not isinstance(
                    provider, ResumableVideoGenerationProvider
                ):
                    raise ShotMillError(
                        "GENERATION_INTERRUPTED",
                        "应用关闭时视频仍在生成，当前服务无法恢复原任务，请检查后重新提交。",
                        409,
                    )
                response = await provider.resume(job.id)
            else:
                request = self._provider_request(job)
                self._validate_capability(request, provider)
                if job.execution_context and isinstance(
                    provider, ValidatingVideoGenerationProvider
                ):
                    await provider.validate(request)
                response = await provider.generate(request)

            created_results: list[Result] = []
            for output in response.outputs:
                relative = self.storage.write_output(
                    project_id, job.id, output.filename, output.content
                )
                url = self.storage.media_url(project_id, relative)
                preview_url = url if (output.content_type or "").startswith("image/") else None
                created_results.append(
                    result_with_preview(
                        Result(
                            id=new_id("result"),
                            project_id=project_id,
                            task_id=task_id,
                            job_id=job.id,
                            video_url=url,
                            preview_url=preview_url,
                            metadata={"contentType": output.content_type, **output.metadata},
                        ),
                        self.storage,
                    )
                )
            if not created_results:
                raise ShotMillError(
                    "GENERATION_NO_RESULT",
                    "Generation provider returned no outputs",
                    502,
                )

            with self.uow_factory() as uow:
                current_job = uow.jobs.get(job.id)
                current_task = uow.tasks.get(task_id)
                if current_job is None or current_task is None:
                    raise RuntimeError("Job or task disappeared during generation")
                for result in created_results:
                    uow.results.add(result)
                old_primary = current_task.primary_result_id
                current_task.primary_result_id = created_results[0].id
                current_task.state = TaskState.COMPLETED
                current_task.progress = 100.0
                current_task.updated_at = utcnow()
                uow.tasks.update(current_task)
                if old_primary != current_task.primary_result_id:
                    uow.contexts.mark_stale_by_source(current_task.id)
                current_job.status = JobStatus.COMPLETED
                current_job.provider_job_id = response.provider_job_id
                current_job.completed_at = utcnow()
                uow.jobs.update_runtime(current_job)

            for result in created_results:
                await self.events.publish(
                    project_id,
                    "task.result_added",
                    taskId=task_id,
                    resultId=result.id,
                )
            await self.events.publish(
                project_id,
                "task.status_changed",
                taskId=task_id,
                status="completed",
                progress=100,
            )
            await self.events.publish(
                project_id, "project.runtime_changed", taskId=None, state="idle"
            )
            await self.events.publish(project_id, "project.summary_changed")
        except Exception as exc:
            if project_id is not None and task_id is not None:
                with self.uow_factory() as uow:
                    failed_job = uow.jobs.get(job_id)
                    failed_task = uow.tasks.get(task_id)
                    if failed_job is not None:
                        failed_job.status = JobStatus.FAILED
                        failed_job.completed_at = utcnow()
                        failed_job.error_code = getattr(exc, "code", type(exc).__name__.upper())
                        failed_job.error_message = str(exc)
                        uow.jobs.update_runtime(failed_job)
                    if failed_task is not None:
                        failed_task.state = TaskState.FAILED
                        failed_task.progress = None
                        failed_task.updated_at = utcnow()
                        uow.tasks.update(failed_task)
                await self.events.publish(
                    project_id,
                    "task.status_changed",
                    taskId=task_id,
                    status="failed",
                    progress=None,
                )
                await self.events.publish(
                    project_id, "project.runtime_changed", taskId=None, state="failed"
                )
            # The failure is persisted; worker stays alive for later jobs.


class GenerationQueue:
    def __init__(self, service: GenerationService, workers: int = 1) -> None:
        self.service = service
        self.workers = max(1, workers)
        self._queue: asyncio.Queue[str | None] = ManagedQueue(service.uow_factory)
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._recovery_ids: set[str] = set()

    async def start(self) -> None:
        if self._started:
            return
        with self.service.uow_factory() as uow:
            jobs = uow.jobs.list_active()
        self._recovery_ids = {job.id for job in jobs if job.status == JobStatus.RUNNING}
        self._started = True
        self._tasks = [
            asyncio.create_task(self._worker(), name=f"shotmill-generation-{index}")
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
                recover = job_id in self._recovery_ids
                self._recovery_ids.discard(job_id)
                await self.service.execute(job_id, recover=recover)
            finally:
                self._queue.task_done()
