import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from shotmill.application.legacy_file_references import (
    release_unused_legacy_paths,
    task_history_media_paths,
)
from shotmill.application.lifecycle_service import LifecycleService
from shotmill.application.result_archive_service import ResultArchiveService
from shotmill.application.snapshot_files import release_unused_shared_aliases, shared_history_owners
from shotmill.domain.entities import Job, PendingFileCleanup, new_id
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.media.cleanup_storage import CleanupStorage


@dataclass(frozen=True)
class PermanentDeleteOutcome:
    deleted_ids: list[str]
    archived_result_count: int
    cleanup_id: str


class PermanentDeleteService:
    def __init__(
        self, uow_factory: Callable[[], UnitOfWork], archive: ResultArchiveService,
        storage: CleanupStorage,
    ):
        self.uow_factory = uow_factory
        self.archive = archive
        self.storage = storage

    def _media_path(self, project_id: str, url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlsplit(url)
        prefix = f"/media/{project_id}/"
        path = unquote(parsed.path)
        if parsed.scheme or parsed.netloc or not path.startswith(prefix):
            return None  # External originals are never cleanup candidates.
        relative = path[len(prefix):]
        self.storage.resolve(project_id, relative)
        return relative

    def purge_tasks(
        self, project_id: str, task_ids: list[str], *, archive_results: bool = True,
    ) -> PermanentDeleteOutcome:
        if not task_ids or len(set(task_ids)) != len(task_ids):
            raise ShotMillError("INVALID_TASK_SELECTION", "请选择不重复的任务。", 422)
        return self._purge(project_id, task_ids, archive_results=archive_results)

    def _job_cache_paths(self, job: Job) -> set[str]:
        """Only cache identities explicitly recorded by persisted execution inputs."""
        paths = set()
        for context in (job.context_snapshot, job.execution_context or {}):
            for media in context.get("media", []):
                path = media.get("projectRelativePath") if isinstance(media, dict) else None
                if isinstance(path, str) and re.fullmatch(r"context/[0-9a-f]{64}\.(png|mp4)", path):
                    self.storage.resolve(job.project_id, path)
                    paths.add(path)
        return paths

    def purge_project(
        self, project_id: str, *, archive_results: bool = True,
    ) -> PermanentDeleteOutcome:
        return self._purge(project_id, None, archive_results=archive_results)

    def _purge(
        self, project_id: str, task_ids: list[str] | None, *, archive_results: bool,
    ) -> PermanentDeleteOutcome:
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在")
            whole_project = task_ids is None
            all_tasks = uow.tasks.list_by_project(project_id)
            selected = {task.id for task in all_tasks} if whole_project else set(task_ids)
            tasks = [task for task in all_tasks if task.id in selected]
            if len(tasks) != len(selected):
                raise NotFoundError("TASK_NOT_FOUND", "任务不存在于当前项目")
            if whole_project:
                if project.deleted_at is None:
                    raise ConflictError("NOT_IN_TRASH", "请先将项目移入回收站")
            elif any(task.deleted_at is None for task in tasks):
                raise ConflictError("NOT_IN_TRASH", "只能永久删除回收站中的任务")
            LifecycleService._ensure_idle(uow, project_id, selected)
            paths: set[str] = set()
            if whole_project:
                # A project directory may contain user exports or originals that
                # were never imported. Its location alone does not grant ownership.
                for asset in uow.assets.list_by_project(project_id):
                    for path in (asset.project_relative_path, asset.thumbnail_path):
                        if path:
                            self.storage.resolve(project_id, path)
                            paths.add(path)
            for task in tasks:
                paths.update(task_history_media_paths(uow, task.id))
                for result in uow.results.list_by_task(task.id):
                    for url in (result.video_url, result.preview_url):
                        path = self._media_path(project_id, url)
                        if path:
                            paths.add(path)
                for job in uow.jobs.list_by_task(task.id):
                    paths.update(self.storage.files(project_id, f"outputs/{job.id}"))
                    paths.update(self._job_cache_paths(job))
            archived = (
                self.archive.archive_in(uow, project_id, list(selected)) if archive_results else []
            )
            cleanup = PendingFileCleanup(new_id("cleanup"), project_id, sorted(paths))
            uow.cleanup.add(cleanup)
            if whole_project:
                uow.projects.delete(project_id)
                # Archive and other projects have their own references. Never
                # delete global bytes here; only release this removed scope.
                uow.files.release_scope("project", project_id)
            else:
                aliases = set(paths)
                for task in tasks:
                    aliases.update(task_history_media_paths(uow, task.id))
                historical = shared_history_owners(
                    uow, project_id, excluding_tasks=frozenset(selected),
                )
                for task in tasks:
                    # Archive ownership has already been established above.
                    # Collect owners before task deletion cascades their rows.
                    for kind, repository in (
                        ("result", uow.results), ("job", uow.jobs),
                        ("prompt_job", uow.prompt_jobs),
                    ):
                        for owner in repository.list_by_task(task.id):
                            if (kind, owner.id) not in historical:
                                uow.files.release_owner("project", project_id, kind, owner.id)
                    uow.tasks.delete(task.id)
                release_unused_legacy_paths(uow, project_id, aliases)
                release_unused_shared_aliases(uow, project_id, aliases)
            return PermanentDeleteOutcome(
                [project_id] if whole_project else [task.id for task in tasks],
                len(archived), cleanup.id,
            )

    def _live_paths(self, uow: UnitOfWork, project_id: str) -> set[str]:
        paths = set()
        for asset in uow.assets.list_by_project(project_id):
            paths.add(asset.project_relative_path)
            if asset.thumbnail_path:
                paths.add(asset.thumbnail_path)
        for task in uow.tasks.list_by_project(project_id):
            paths.update(task_history_media_paths(uow, task.id))
            for job in uow.jobs.list_by_task(task.id):
                paths.update(self._job_cache_paths(job))
            for result in uow.results.list_by_task(task.id):
                for url in (result.video_url, result.preview_url):
                    path = self._media_path(project_id, url)
                    if path:
                        paths.add(path)
        # Normalize aliases before comparing against deletion candidates.
        root = self.storage.resolve(project_id)
        return {
            self.storage.resolve(project_id, path).relative_to(root).as_posix() for path in paths
        }

    def cleanup_pending(self) -> int:
        """Retry durable cleanup; active jobs retain all project media until terminal."""
        completed = 0
        with self.uow_factory() as uow:
            uow.reserve_write()
            for item in uow.cleanup.list():
                if (uow.jobs.active_task_ids_by_project(item.project_id)
                        or uow.prompt_jobs.active_task_ids_by_project(item.project_id)):
                    continue
                try:
                    live = self._live_paths(uow, item.project_id)
                    root = self.storage.resolve(item.project_id)
                    for path in item.paths:
                        normalized = self.storage.resolve(item.project_id, path).relative_to(root)
                        if normalized.as_posix() not in live:
                            self.storage.delete_file(item.project_id, path)
                except (OSError, ValueError) as exc:
                    uow.cleanup.fail(item.id, str(exc))
                    continue
                uow.cleanup.delete(item.id)
                completed += 1
        return completed
