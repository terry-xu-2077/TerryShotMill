from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from shotmill.application.context_duration import previous_video_duration
from shotmill.application.continuation_risks import continuation_risks, continuation_status
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
    ProjectRuntimeView,
    ProjectSettingsView,
    ProjectSummary,
    ProjectWorkspaceView,
    TaskEditorView,
    WorkspaceProject,
)
from shotmill.frontend_adapter.runtime import prompt_batch_runtime, video_job_runtime
from shotmill.frontend_adapter.timing import task_timing
from shotmill.media.previews import result_with_preview
from shotmill.media.storage import MediaStorage


class WorkspaceQuery:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage) -> None:
        self.uow_factory = uow_factory
        self.storage = storage

    def _results(self, uow: UnitOfWork, task_id: str):
        return [
            result_with_preview(result, self.storage)
            for result in uow.results.list_by_task(task_id)
        ]

    def list_projects(self) -> list[ProjectSummary]:
        with self.uow_factory() as uow:
            items: list[ProjectSummary] = []
            for project in uow.projects.list():
                tasks = uow.tasks.list_by_project(project.id)
                results_by_task = {task.id: self._results(uow, task.id) for task in tasks}
                items.append(
                    map_project_summary(
                        project,
                        tasks,
                        uow.assets.count_by_project(project.id),
                        results_by_task,
                        asset_previews={
                            asset.id: asset_preview_url(asset, self.storage)
                            for asset in uow.assets.list_by_project(project.id)
                        },
                    )
                )
                self._project_notifications(uow, items[-1], tasks)
            return items

    @staticmethod
    def _project_notifications(uow, summary, tasks):
        for task in tasks:
            revisions = uow.prompt_revisions.list_by_task(task.id)
            if revisions:
                summary.new_results.append(
                    {
                        "prompt": max(revisions, key=lambda revision: revision.created_at).id,
                    }
                )
            summary.generation_warnings.extend(
                f"{task.title}：{warning}" for warning in continuation_risks(uow, task)
            )
        return summary

    def project_summary(self, project_id: str) -> ProjectSummary:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = uow.tasks.list_by_project(project_id)
            results_by_task = {task.id: self._results(uow, task.id) for task in tasks}
            summary = map_project_summary(
                project,
                tasks,
                uow.assets.count_by_project(project_id),
                results_by_task,
                asset_previews={
                    asset.id: asset_preview_url(asset, self.storage)
                    for asset in uow.assets.list_by_project(project_id)
                },
            )

            return self._project_notifications(uow, summary, tasks)

    def project_settings(self, project_id: str) -> ProjectSettingsView:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = uow.tasks.list_by_project(project_id)
            assets = uow.assets.list_by_project(project_id)
            results = {task.id: self._results(uow, task.id) for task in tasks}
            previews = {asset.id: asset_preview_url(asset, self.storage) for asset in assets}
            automatic = map_project_summary(
                replace(project, cover_asset_id=None),
                tasks,
                len(assets),
                results,
                asset_previews=previews,
            ).cover_url
            return ProjectSettingsView(
                id=project.id,
                title=project.title,
                description=project.description,
                use_description_for_ai_prompt=project.use_description_for_ai_prompt,
                cover_asset_id=project.cover_asset_id,
                cover_url=(
                    previews.get(project.cover_asset_id) if project.cover_asset_id else automatic
                ),
                automatic_cover_url=automatic,
            )

    def workspace(self, project_id: str) -> ProjectWorkspaceView:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = uow.tasks.list_by_project(project_id)
            active_prompt_task_ids = uow.prompt_jobs.active_task_ids_by_project(project_id)
            active_video_task_ids = uow.jobs.active_task_ids_by_project(project_id)
            asset_previews = {
                asset.id: asset_preview_url(asset, self.storage)
                for asset in uow.assets.list_by_project(project_id)
            }
            summaries = [
                map_task_summary(
                    task,
                    self._results(uow, task.id),
                    has_active_prompt_job=task.id in active_prompt_task_ids,
                    has_active_video_job=task.id in active_video_task_ids,
                    asset_previews=asset_previews,
                )
                for task in tasks
            ]
            for summary in summaries:
                summary.generation_status_note = continuation_status(
                    uow, next(task for task in tasks if task.id == summary.id)
                )
                summary.generation_warnings = continuation_risks(
                    uow, next(task for task in tasks if task.id == summary.id)
                )
                revisions = uow.prompt_revisions.list_by_task(summary.id)
                summary.latest_prompt_revision_id = (
                    max(revisions, key=lambda revision: revision.created_at).id
                    if revisions
                    else None
                )
                summary.timing = task_timing(
                    uow.jobs.list_by_task(summary.id),
                    revisions,
                    uow.prompt_jobs.list_by_task(summary.id),
                )
            runtime = self._runtime(uow, project_id, tasks)
            return ProjectWorkspaceView(
                project=WorkspaceProject(id=project.id, title=project.title),
                tasks=summaries,
                runtime=runtime,
            )

    def _runtime(self, uow, project_id, tasks):
        active_job = uow.jobs.latest_active_by_project(project_id)
        active_task = uow.tasks.get(active_job.task_id) if active_job else None
        runtime = map_runtime(active_job, active_task)
        titles = {task.id: task.title for task in tasks}
        runtime.prompt_batches = [
            prompt_batch_runtime(batch, uow.prompt_jobs.list_by_batch(batch.id), titles)
            for batch in uow.prompt_batches.list_by_project(project_id)
        ]
        runtime.video_jobs = [
            video_job_runtime(job, task.title)
            for task in tasks
            for job in reversed(uow.jobs.list_by_task(task.id))
        ]
        positions = {}
        for repository in (uow.jobs, uow.prompt_jobs):
            queued = [job for job in repository.list_active() if job.status.value == "queued"]
            priorities = {job.id: uow.runtime_controls.get(job.id).position for job in queued}
            queued.sort(
                key=lambda job: (
                    priorities[job.id] if priorities[job.id] is not None else float("inf")
                )
            )
            positions.update({job.id: index for index, job in enumerate(queued)})

        def visible(items):
            result = []
            for item in items:
                control = uow.runtime_controls.get(item.id)
                if control.hidden:
                    continue
                item.paused = control.paused
                item.position = positions.get(item.id)
                result.append(item)
            return sorted(
                result,
                key=lambda item: item.position if item.position is not None else float("inf"),
            )

        runtime.video_jobs = visible(runtime.video_jobs)
        for batch in runtime.prompt_batches:
            batch.items = visible(batch.items)
            batch.queued_count = sum(item.state == "queued" for item in batch.items)
            batch.failed_count = sum(item.state == "failed" for item in batch.items)
            batch.completed_count = sum(item.state == "completed" for item in batch.items)
            batch.cancelled_count = sum(item.state == "cancelled" for item in batch.items)
            batch.running_count = sum(item.state == "running" for item in batch.items)
        return runtime

    def global_runtime(self) -> list[ProjectRuntimeView]:
        with self.uow_factory() as uow:
            return [
                ProjectRuntimeView(
                    project=WorkspaceProject(id=project.id, title=project.title),
                    runtime=self._runtime(uow, project.id, uow.tasks.list_by_project(project.id)),
                )
                for project in uow.projects.list()
            ]

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
            return map_task_editor(task, previous_video_duration(uow, previous, self.storage))

    def task_summary(self, project_id: str, task_id: str):
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            summary = map_task_summary(
                task,
                self._results(uow, task.id),
                has_active_prompt_job=(
                    task.id in uow.prompt_jobs.active_task_ids_by_project(project_id)
                ),
                has_active_video_job=task.id in uow.jobs.active_task_ids_by_project(project_id),
                asset_previews={
                    asset.id: asset_preview_url(asset, self.storage)
                    for asset in uow.assets.list_by_project(project_id)
                },
            )
            revisions = uow.prompt_revisions.list_by_task(task_id)
            summary.generation_warnings = continuation_risks(uow, task)
            summary.latest_prompt_revision_id = (
                max(revisions, key=lambda revision: revision.created_at).id if revisions else None
            )
            summary.timing = task_timing(
                uow.jobs.list_by_task(task_id),
                revisions,
                uow.prompt_jobs.list_by_task(task_id),
            )
            return summary

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
