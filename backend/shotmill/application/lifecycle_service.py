from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from shotmill.domain.entities import Project, Task, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError

LifecycleAction = Literal["archive", "unarchive", "trash", "restore"]
LifecycleScope = Literal["active", "archived", "trash"]


def in_lifecycle_scope(item: Project | Task, scope: LifecycleScope) -> bool:
    if scope == "trash":
        return item.deleted_at is not None
    if scope == "archived":
        return item.deleted_at is None and item.archived_at is not None
    return item.deleted_at is None and item.archived_at is None


@dataclass(frozen=True, slots=True)
class DeletionImpact:
    source_task_id: str
    source_task_title: str
    target_task_id: str
    target_task_title: str
    kind: str
    source_result_id: str | None


def require_writable(project: Project, task: Task | None = None) -> None:
    for item in (project, task):
        if item is not None and (item.archived_at is not None or item.deleted_at is not None):
            raise ConflictError("OBJECT_READ_ONLY", "请先恢复对象并取消归档，再继续编辑或生成。")


def apply_transition(item: Project | Task, action: LifecycleAction) -> None:
    if action not in {"archive", "unarchive", "trash", "restore"}:
        raise ShotMillError("INVALID_LIFECYCLE_ACTION", "不支持的生命周期操作。", 422)
    if item.deleted_at is not None and action in {"archive", "unarchive"}:
        raise ConflictError("OBJECT_IN_TRASH", "请先从回收站恢复。")
    now = utcnow()
    if action == "archive":
        item.archived_at = item.archived_at or now
    elif action == "unarchive":
        item.archived_at = None
    elif action == "trash":
        item.deleted_at = item.deleted_at or now
    else:
        item.deleted_at = None
    item.updated_at = now


class LifecycleService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self.uow_factory = uow_factory

    def deletion_impacts(self, project_id: str, task_ids: list[str]) -> list[DeletionImpact]:
        """Only dependencies crossing the selected deletion boundary are affected."""
        selected = set(task_ids)
        if not selected or len(selected) != len(task_ids):
            raise ShotMillError("INVALID_TASK_SELECTION", "请选择不重复的任务。", 422)
        with self.uow_factory() as uow:
            self._project(uow, project_id)
            tasks = uow.tasks.list_by_project(project_id)
            by_id = {task.id: task for task in tasks}
            if not selected <= by_id.keys():
                raise NotFoundError("TASK_NOT_FOUND", "任务不存在于当前项目。")
            impacts = []
            for target in tasks:
                if target.id in selected:
                    continue
                for link in uow.contexts.list_by_target(target.id):
                    if link.source_task_id in selected:
                        source = by_id[link.source_task_id]
                        impacts.append(DeletionImpact(
                            source_task_id=source.id,
                            source_task_title=source.title,
                            target_task_id=target.id,
                            target_task_title=target.title,
                            kind=link.kind,
                            source_result_id=link.source_result_id,
                        ))
            return impacts

    @staticmethod
    def _project(uow: UnitOfWork, project_id: str) -> Project:
        project = uow.projects.get(project_id)
        if project is None:
            raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在。")
        return project

    @staticmethod
    def _ensure_idle(uow: UnitOfWork, project_id: str, task_ids: set[str]) -> None:
        active = (
            uow.jobs.active_task_ids_by_project(project_id)
            | uow.prompt_jobs.active_task_ids_by_project(project_id)
        )
        if active & task_ids:
            raise ConflictError("TASK_BUSY", "请先取消相关任务，并等待执行停止。")

    def transition_tasks(
        self, project_id: str, task_ids: list[str], action: LifecycleAction
    ) -> list[Task]:
        if not task_ids or len(set(task_ids)) != len(task_ids):
            raise ShotMillError("INVALID_TASK_SELECTION", "请选择不重复的任务。", 422)
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = self._project(uow, project_id)
            require_writable(project)
            tasks = []
            for task_id in task_ids:
                task = uow.tasks.get(task_id)
                if task is None or task.project_id != project_id:
                    raise NotFoundError("TASK_NOT_FOUND", "任务不存在于当前项目。")
                tasks.append(task)
            self._ensure_idle(uow, project_id, set(task_ids))
            for task in tasks:
                apply_transition(task, action)
                uow.tasks.update(task)
            project.updated_at = utcnow()
            uow.projects.update(project)
            return tasks

    def transition_project(self, project_id: str, action: LifecycleAction) -> Project:
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = self._project(uow, project_id)
            task_ids = {task.id for task in uow.tasks.list_by_project(project_id)}
            self._ensure_idle(uow, project_id, task_ids)
            apply_transition(project, action)
            uow.projects.update(project)
            return project
