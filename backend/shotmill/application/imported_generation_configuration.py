"""Explicit destination configuration for imported tasks; history stays immutable."""

from collections.abc import Callable
from dataclasses import dataclass

from shotmill.application.lifecycle_service import require_writable
from shotmill.domain.entities import utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class PendingGenerationConfiguration:
    task_id: str
    title: str
    revision: int
    source_configuration_id: str | None
    read_only: bool


class ImportedGenerationConfiguration:
    def __init__(self, factory: Callable[[], UnitOfWork], available_ids: Callable[[], set[str]]):
        self.factory = factory
        self.available_ids = available_ids

    def pending(self, project_id: str) -> list[PendingGenerationConfiguration]:
        with self.factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在。")
            return [PendingGenerationConfiguration(
                task.id, task.title, task.revision,
                task.generation_params.get("workflowProfileId")
                or task.generation_params.get("profileId"),
                bool(project.archived_at or project.deleted_at
                     or task.archived_at or task.deleted_at),
            ) for task in uow.tasks.list_by_project(project_id)
                if uow.tasks.generation_configuration_required(task.id)]

    def confirm(self, project_id: str, task_id: str, configuration_id: str, revision: int) -> None:
        # The adapter supplies locally configured IDs; matching an imported label
        # alone is never a confirmation. Ordinary provider validation still runs.
        if not configuration_id or configuration_id not in self.available_ids():
            raise ConflictError(
                "WORKFLOW_PROFILE_UNAVAILABLE", "请选择本机已启用且已配置的工作流。",
            )
        with self.factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            task = uow.tasks.get(task_id)
            if project is None or task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "任务不存在。")
            require_writable(project, task)
            if not uow.tasks.generation_configuration_required(task_id):
                raise ConflictError(
                    "GENERATION_CONFIGURATION_CONFIRMED", "任务配置已确认，请刷新列表。",
                )
            if task.revision != revision:
                raise ConflictError("TASK_REVISION_CONFLICT", "任务已变化，请刷新后重新确认。")
            if task_id in uow.jobs.active_task_ids_by_project(project_id):
                raise ConflictError("TASK_BUSY", "任务正在生成，请稍后重试。")
            task.generation_params = {
                **task.generation_params, "workflowProfileId": configuration_id,
            }
            task.generation_params.pop("profileId", None)
            # Retain imported media slot selections. The workflow adapter must
            # validate their compatibility rather than silently discard inputs.
            task.revision += 1
            task.updated_at = utcnow()
            uow.tasks.update(task)
            uow.tasks.set_generation_configuration_required(task_id, False)
