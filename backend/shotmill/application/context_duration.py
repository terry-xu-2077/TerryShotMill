from shotmill.domain.entities import Task
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ShotMillError
from shotmill.media.context import video_duration
from shotmill.media.storage import MediaStorage


def previous_video_duration(
    uow: UnitOfWork, task: Task | None, storage: MediaStorage | None
) -> float | None:
    if task is None:
        return None
    result = uow.results.get(task.primary_result_id) if task.primary_result_id else None
    if result and result.project_id == task.project_id and result.task_id == task.id and storage:
        prefix = f"/media/{task.project_id}/"
        if result.video_url.startswith(prefix):
            try:
                return video_duration(
                    storage.resolve(task.project_id, result.video_url[len(prefix) :])
                )
            except (ShotMillError, ValueError):
                # The editor remains usable; generation rejects unreadable context separately.
                pass
    return task.planned_duration_seconds
