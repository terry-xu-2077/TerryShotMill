from __future__ import annotations

from datetime import UTC, datetime

from shotmill.domain.entities import Job, PromptEnhancementBatch, PromptEnhancementJob
from shotmill.frontend_adapter.models import PromptBatchRuntime, RuntimeTaskItem

_PROMPT_ERRORS = {
    "USER_PROMPT_REQUIRED": "缺少用户提示词，请补充后重新增强。",
    "PROMPT_JOB_STALE": "排队后任务内容已修改，请使用当前内容重新增强。",
    "PROVIDER_UNAVAILABLE": "增强服务不可用，请检查连接后重试。",
    "GENERATION_SERVICE_OFFLINE": "增强服务不可用，请检查连接后重试。",
    "PROMPT_PROVIDER_MEDIA_UNSUPPORTED": "当前增强服务不支持所选媒体类型。",
    "ASSET_NOT_FOUND": "引用的资产已不存在，请重新选择素材。",
    "TASK_NOT_FOUND": "任务已不存在。",
    "PROMPT_PROFILE_SNAPSHOT_MISSING": "旧增强任务缺少完整配置，请重新提交增强。",
    "PROMPT_PROFILE_UNAVAILABLE": "原增强服务不可用，请检查设置。",
    "PROMPT_CREDENTIAL_CHANGED": "增强服务凭据已变化，请重新提交增强。",
    "active-prompt-job": "任务已在增强队列中，已跳过重复提交。",
}


def elapsed(start: datetime | None, end: datetime | None) -> float | None:
    if start is None:
        return None
    start = start.replace(tzinfo=UTC) if start.tzinfo is None else start
    end = end or datetime.now(UTC)
    end = end.replace(tzinfo=UTC) if end.tzinfo is None else end
    return max(0.0, (end - start).total_seconds())


def prompt_batch_runtime(
    batch: PromptEnhancementBatch,
    jobs: list[PromptEnhancementJob],
    task_titles: dict[str, str],
) -> PromptBatchRuntime:
    return PromptBatchRuntime(
        id=batch.id,
        created_at=batch.created_at,
        state=batch.status,
        completed_count=sum(job.status.value == "completed" for job in jobs),
        failed_count=sum(job.status.value == "failed" for job in jobs),
        cancelled_count=sum(job.status.value == "cancelled" for job in jobs),
        queued_count=sum(job.status.value == "queued" for job in jobs),
        running_count=sum(job.status.value == "running" for job in jobs),
        items=[
            RuntimeTaskItem(
                id=job.id,
                task_id=job.task_id,
                title=task_titles.get(job.task_id, "已删除任务"),
                state=job.status.value,
                elapsed_seconds=elapsed(job.started_at, job.finished_at),
                error=_PROMPT_ERRORS.get(job.error, job.error),
            )
            for job in jobs
        ],
    )


def video_job_runtime(job: Job, title: str) -> RuntimeTaskItem:
    return RuntimeTaskItem(
        id=job.id,
        task_id=job.task_id,
        title=title,
        state=job.status.value,
        status_note=(
            "等待上一任务结果"
            if job.status.value == "queued"
            and job.context_snapshot.get("dependency")
            and job.execution_context is None
            else None
        ),
        continuation_fallback=job.error_code == "CONTEXT_DEPENDENCY_UNAVAILABLE"
        and job.execution_context is None,
        elapsed_seconds=elapsed(job.started_at, job.completed_at),
        error=job.error_message or job.error_code,
    )
