from __future__ import annotations

from collections.abc import Callable

from shotmill.application.lifecycle_service import require_writable
from shotmill.domain.entities import Result, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError


class ResultService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self.uow_factory = uow_factory

    def list(self, project_id: str, task_id: str) -> list[Result]:
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            return uow.results.list_by_task(task_id)

    def select_primary(self, project_id: str, task_id: str, result_id: str) -> Result:
        with self.uow_factory() as uow:
            uow.reserve_write()
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            require_writable(project, task)
            result = uow.results.get(result_id)
            if result is None or result.task_id != task_id:
                raise NotFoundError("RESULT_NOT_FOUND", "Result not found")
            if task.primary_result_id != result_id:
                task.primary_result_id = result_id
                task.updated_at = utcnow()
                task.revision += 1
                uow.tasks.update(task)
                uow.contexts.mark_stale_by_source(task.id)
            return result
