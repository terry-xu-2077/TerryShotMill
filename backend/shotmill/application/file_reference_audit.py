"""Fail closed when business records disagree with global ownership before GC."""

import re
from urllib.parse import unquote, urlsplit

from shotmill.application.legacy_file_references import task_history_media_paths
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError


def audit_file_references(uow: UnitOfWork, candidates: set[str]) -> None:
    def invalid():
        raise ConflictError("FILE_REFERENCE_INCONSISTENT", "文件引用不一致，已停止清理。")

    def check_path(project_id: str, path: str | None):
        if not path or not path.startswith("shared/"):
            return
        match = re.fullmatch(r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", path)
        ref = uow.files.get_reference("project", project_id, *match.groups()) if match else None
        if ref is None or uow.files.get(ref.sha256) is None:
            invalid()

    # Check the current project records before collecting shared files.
    for project in uow.projects.list():
        for asset in uow.assets.list_by_project(project.id):
            if asset.hash in candidates:
                invalid()
            check_path(project.id, asset.project_relative_path)
            check_path(project.id, asset.thumbnail_path)
        for task in uow.tasks.list_by_project(project.id):
            for path in task_history_media_paths(uow, task.id):
                check_path(project.id, path)
            for result in uow.results.list_by_task(task.id):
                if result.metadata.get("sha256") in candidates:
                    invalid()
                for url in (result.video_url, result.preview_url):
                    if not url:
                        continue
                    path = unquote(urlsplit(url).path)
                    prefix = f"/media/{project.id}/"
                    if path.startswith(prefix):
                        check_path(project.id, path[len(prefix):])
