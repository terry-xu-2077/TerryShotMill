from collections.abc import Sequence
from datetime import UTC, datetime

from shotmill.domain.entities import AiPromptRevision, Job, PromptEnhancementJob, utcnow
from shotmill.domain.enums import JobStatus
from shotmill.frontend_adapter.models import TaskTiming


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _durations(
    created: datetime, started: datetime | None, finished: datetime | None,
    status: JobStatus, now: datetime,
) -> tuple[float | None, float | None]:
    queue_end = started or finished or (now if status == JobStatus.QUEUED else None)
    queued = max(0, (_utc(queue_end) - _utc(created)).total_seconds()) if queue_end else None
    execution_end = finished or (now if status == JobStatus.RUNNING else None)
    executed = (
        max(0, (_utc(execution_end) - _utc(started)).total_seconds())
        if started and execution_end else None
    )
    return queued, executed


def task_timing(
    jobs: list[Job], revisions: list[AiPromptRevision],
    prompt_jobs: Sequence[PromptEnhancementJob] = (),
) -> TaskTiming:
    latest = max(jobs, key=lambda item: _utc(item.submitted_at), default=None)
    revision = max(revisions, key=lambda item: _utc(item.created_at), default=None)
    now = utcnow()
    timing = TaskTiming(
        prompt_seconds=revision.elapsed_seconds if revision else None, measured_at=now
    )
    prompt = max(
        (item for item in prompt_jobs if item.error != "active-prompt-job"),
        key=lambda item: _utc(item.created_at), default=None,
    )
    if prompt and (
        not revision or prompt.revision_id == revision.id
        or _utc(prompt.created_at) >= _utc(revision.created_at)
    ):
        timing.prompt_queue_seconds, timing.prompt_seconds = _durations(
            prompt.created_at, prompt.started_at, prompt.finished_at, prompt.status, now
        )
        timing.prompt_running = prompt.status == JobStatus.RUNNING
        timing.prompt_queued = prompt.status == JobStatus.QUEUED
    if latest is None:
        return timing
    timing.video_queue_seconds, timing.video_seconds = _durations(
        latest.submitted_at, latest.started_at, latest.completed_at, latest.status, now
    )
    timing.generation_progress = latest.runtime_progress
    timing.video_running = latest.status == JobStatus.RUNNING
    timing.video_queued = latest.status == JobStatus.QUEUED
    return timing
