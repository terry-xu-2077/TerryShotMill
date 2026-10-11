"""Direct task deletion and removal of a project from the recent list."""

from collections.abc import Callable
from dataclasses import dataclass

from shotmill.application.legacy_file_references import (
    release_unused_legacy_paths,
    task_history_media_paths,
)
from shotmill.application.snapshot_files import release_unused_shared_aliases, shared_history_owners
from shotmill.domain.entities import utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError


@dataclass(frozen=True, slots=True)
class DeletionImpact:
    source_task_id: str
    source_task_title: str
    target_task_id: str
    target_task_title: str
    kind: str
    source_result_id: str | None


class RemovalService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self.uow_factory = uow_factory

    @staticmethod
    def _ensure_idle(uow: UnitOfWork, project_id: str, task_ids: set[str]) -> None:
        active = (uow.jobs.active_task_ids_by_project(project_id)
                  | uow.prompt_jobs.active_task_ids_by_project(project_id))
        if active & task_ids:
            raise ConflictError("TASK_BUSY", "请先取消相关任务，并等待执行停止。")

    def deletion_impacts(self, project_id: str, task_ids: list[str]) -> list[DeletionImpact]:
        selected = set(task_ids)
        if not selected or len(selected) != len(task_ids):
            raise ShotMillError("INVALID_TASK_SELECTION", "请选择不重复的任务。", 422)
        with self.uow_factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在。")
            tasks = uow.tasks.list_by_project(project_id)
            by_id = {task.id: task for task in tasks}
            if not selected <= by_id.keys():
                raise NotFoundError("TASK_NOT_FOUND", "任务不存在于当前项目。")
            return [DeletionImpact(
                source_task_id=link.source_task_id,
                source_task_title=by_id[link.source_task_id].title,
                target_task_id=target.id,
                target_task_title=target.title,
                kind=link.kind,
                source_result_id=link.source_result_id,
            ) for target in tasks if target.id not in selected
              for link in uow.contexts.list_by_target(target.id)
              if link.source_task_id in selected]

    def delete_tasks(self, project_id: str, task_ids: list[str]) -> list[str]:
        selected = set(task_ids)
        if not selected or len(selected) != len(task_ids):
            raise ShotMillError("INVALID_TASK_SELECTION", "请选择不重复的任务。", 422)
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在。")
            tasks = [task for task in uow.tasks.list_by_project(project_id)
                     if task.id in selected]
            if len(tasks) != len(selected):
                raise NotFoundError("TASK_NOT_FOUND", "任务不存在于当前项目。")
            self._ensure_idle(uow, project_id, selected)
            paths = set().union(*(task_history_media_paths(uow, task.id) for task in tasks))
            protected = shared_history_owners(uow, project_id, excluding_tasks=frozenset(selected))
            for task in tasks:
                for kind, repository in (("result", uow.results), ("job", uow.jobs),
                                         ("prompt_job", uow.prompt_jobs)):
                    for owner in repository.list_by_task(task.id):
                        if (kind, owner.id) not in protected:
                            uow.files.release_owner("project", project_id, kind, owner.id)
                uow.tasks.delete(task.id)
            release_unused_legacy_paths(uow, project_id, paths)
            release_unused_shared_aliases(uow, project_id, paths)
            project.updated_at = utcnow()
            uow.projects.update(project)
            return task_ids

    def remove_project(self, project_id: str) -> None:
        """Forget the opened project; leave its engineering file and media untouched."""
        with self.uow_factory() as uow:
            uow.reserve_write()
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在。")
            self._ensure_idle(uow, project_id,
                              {task.id for task in uow.tasks.list_by_project(project_id)})
            uow.projects.delete(project_id)
            uow.files.release_scope("project", project_id)
