from __future__ import annotations

from collections.abc import Callable

from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError
from shotmill.frontend_adapter.mapper import (
    asset_preview_url,
    map_asset,
    map_asset_reference,
    map_project_summary,
    map_runtime,
    map_task_editor,
    map_task_summary,
)
from shotmill.frontend_adapter.models import (
    AssetReferenceItem,
    ProjectAssetView,
    ProjectSettingsView,
    ProjectSummary,
    ProjectWorkspaceView,
    TaskEditorView,
    WorkspaceProject,
)
from shotmill.media.storage import MediaStorage


class WorkspaceQuery:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage) -> None:
        self.uow_factory = uow_factory
        self.storage = storage

    def list_projects(self) -> list[ProjectSummary]:
        with self.uow_factory() as uow:
            items: list[ProjectSummary] = []
            for project in uow.projects.list():
                tasks = uow.tasks.list_by_project(project.id)
                results_by_task = {task.id: uow.results.list_by_task(task.id) for task in tasks}
                items.append(
                    map_project_summary(
                        project,
                        tasks,
                        uow.assets.count_by_project(project.id),
                        results_by_task,
                        asset_previews={asset.id: asset_preview_url(asset, self.storage)
                                        for asset in uow.assets.list_by_project(project.id)},
                    )
                )
            return items

    def project_summary(self, project_id: str) -> ProjectSummary:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = uow.tasks.list_by_project(project_id)
            results_by_task = {task.id: uow.results.list_by_task(task.id) for task in tasks}
            return map_project_summary(
                project,
                tasks,
                uow.assets.count_by_project(project_id),
                results_by_task,
                asset_previews={asset.id: asset_preview_url(asset, self.storage)
                                for asset in uow.assets.list_by_project(project_id)},
            )

    def project_settings(self, project_id: str) -> ProjectSettingsView:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            return ProjectSettingsView(
                id=project.id,
                title=project.title,
                description=project.description,
                use_description_for_ai_prompt=project.use_description_for_ai_prompt,
            )

    def workspace(self, project_id: str) -> ProjectWorkspaceView:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = uow.tasks.list_by_project(project_id)
            active_prompt_task_ids = uow.prompt_jobs.active_task_ids_by_project(project_id)
            active_video_task_ids = uow.jobs.active_task_ids_by_project(project_id)
            asset_previews = {asset.id: asset_preview_url(asset, self.storage)
                              for asset in uow.assets.list_by_project(project_id)}
            summaries = [
                map_task_summary(
                    task,
                    uow.results.list_by_task(task.id),
                    has_active_prompt_job=task.id in active_prompt_task_ids,
                    has_active_video_job=task.id in active_video_task_ids,
                    asset_previews=asset_previews,
                )
                for task in tasks
            ]
            active_job = uow.jobs.latest_active_by_project(project_id)
            active_task = uow.tasks.get(active_job.task_id) if active_job else None
            return ProjectWorkspaceView(
                project=WorkspaceProject(id=project.id, title=project.title),
                tasks=summaries,
                runtime=map_runtime(active_job, active_task),
            )

    def task_editor(self, project_id: str, task_id: str) -> TaskEditorView:
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            tasks = uow.tasks.list_by_project(project_id)
            previous = next(
                (item for item in reversed(tasks) if item.display_order < task.display_order),
                None,
            )
            return map_task_editor(task, previous.planned_duration_seconds if previous else None)

    def task_summary(self, project_id: str, task_id: str):
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            return map_task_summary(
                task,
                uow.results.list_by_task(task.id),
                has_active_prompt_job=(
                    task.id in uow.prompt_jobs.active_task_ids_by_project(project_id)
                ),
                has_active_video_job=task.id in uow.jobs.active_task_ids_by_project(project_id),
                asset_previews={asset.id: asset_preview_url(asset, self.storage)
                                for asset in uow.assets.list_by_project(project_id)},
            )

    def list_assets(
        self,
        project_id: str,
        purpose: str | None = None,
    ) -> list[ProjectAssetView | AssetReferenceItem]:
        with self.uow_factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            assets = uow.assets.list_by_project(project_id)
            if purpose == "prompt-reference":
                return [map_asset_reference(asset, self.storage) for asset in assets]
            return [map_asset(asset, self.storage) for asset in assets]
