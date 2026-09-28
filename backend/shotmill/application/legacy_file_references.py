"""Release selected legacy aliases only after checking every remaining media owner."""

from urllib.parse import unquote, urlsplit

from shotmill.domain.repositories import UnitOfWork
from shotmill.media.legacy_paths import legacy_owner_id


def task_history_media_paths(uow: UnitOfWork, task_id: str) -> set[str]:
    media = []
    for job in uow.jobs.list_by_task(task_id):
        media.extend(job.assets_snapshot)
        media.extend(job.context_snapshot.get("media", []))
        media.extend((job.execution_context or {}).get("media", []))
    for job in uow.prompt_jobs.list_by_task(task_id):
        media.extend(job.source_snapshot.get("media", []))
        media.extend(job.context_snapshot.get("media", []))
    return {item["projectRelativePath"] for item in media
            if isinstance(item.get("projectRelativePath"), str)}


def release_unused_legacy_paths(uow: UnitOfWork, project_id: str, candidates: set[str]) -> None:
    candidates = {path for path in candidates if path and not path.startswith("shared/")}
    if not candidates:
        return
    retained = set()
    for asset in uow.assets.list_by_project(project_id):
        retained.update((asset.project_relative_path, asset.thumbnail_path))
    prefix = f"/media/{project_id}/"
    for task in uow.tasks.list_by_project(project_id):
        for result in uow.results.list_by_task(task.id):
            for url in (result.video_url, result.preview_url):
                if not url:
                    continue
                parsed = urlsplit(url)
                path = unquote(parsed.path)
                if not parsed.scheme and not parsed.netloc and path.startswith(prefix):
                    retained.add(path[len(prefix):])
        retained.update(task_history_media_paths(uow, task.id))
    for path in candidates - retained:
        uow.files.release_owner("project", project_id, "legacy_path", legacy_owner_id(path))
