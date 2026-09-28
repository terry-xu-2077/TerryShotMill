from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit

from shotmill.application.file_library import FileLibrary
from shotmill.domain.entities import ArchivedResult, new_id
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.media.archive_storage import ArchiveStorage
from shotmill.media.storage import MediaStorage


class ResultArchiveService:
    def __init__(
        self, uow_factory: Callable[[], UnitOfWork],
        media: MediaStorage, storage: ArchiveStorage,
        file_library: FileLibrary | None = None,
    ):
        self.uow_factory = uow_factory
        self.media = media
        self.storage = storage
        self.file_library = file_library

    def file_path_in(self, uow: UnitOfWork, record: ArchivedResult, file: dict) -> Path:
        """An archive owns its reference independently of the deleted source project."""
        if file.get("storage") != "shared":
            if not self.storage.verify(file):
                raise ValueError("Legacy archive is damaged")
            return self.storage.resolve(file["path"])
        if self.file_library is None:
            raise ValueError("Shared archive storage is unavailable")
        reference = uow.files.get_reference(
            "archive", record.id, "result", record.source_result_id, file["role"],
        )
        stored = uow.files.get(file["sha256"])
        if (reference is None or stored is None or reference.sha256 != stored.sha256
                or stored.size != file["size"] or stored.storage_path != file["path"]):
            raise ValueError("Archive reference is missing or inconsistent")
        self.file_library.storage.verify(stored)
        return self.file_library.storage.resolve(stored)

    def verify_in(self, uow: UnitOfWork, record: ArchivedResult) -> bool:
        try:
            if not record.files:
                return False
            for file in record.files:
                self.file_path_in(uow, record, file)
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _source(self, project_id: str, url: str) -> Path:
        parsed = urlsplit(url)
        prefix = f"/media/{project_id}/"
        path = unquote(parsed.path)
        if parsed.scheme or parsed.netloc or not path.startswith(prefix):
            raise ValueError("Result must be collected into project storage before archiving")
        root = self.media.projects_root.resolve()
        project_root = (root / project_id).resolve()
        project_root.relative_to(root)
        if project_root == root:
            raise ValueError("Invalid project storage path")
        relative = path[len(prefix):]
        return self.media.resolve_read(project_id, relative)

    def archive_tasks(self, project_id: str, task_ids: list[str]) -> list[ArchivedResult]:
        """Publish the complete selection atomically; copying never removes sources."""
        with self.uow_factory() as uow:
            uow.reserve_write()
            return self.archive_in(uow, project_id, task_ids)

    def archive_in(
        self, uow: UnitOfWork, project_id: str, task_ids: list[str],
    ) -> list[ArchivedResult]:
        """Join the caller's transaction, including permanent deletion when requested."""
        project = uow.projects.get(project_id)
        if project is None:
            raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在")
        tasks = []
        for task_id in dict.fromkeys(task_ids):
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "任务不存在")
            tasks.append(task)
        archived = []
        for task in tasks:
            for result in uow.results.list_by_task(task.id):
                existing = uow.archived_results.get_by_source(result.id)
                if existing is not None:
                    if not self.verify_in(uow, existing):
                        raise ConflictError(
                            "ARCHIVE_DAMAGED", "已有归档文件缺失或损坏，不能删除原结果"
                        )
                    archived.append(existing)
                    continue
                job = uow.jobs.get(result.job_id)
                if job is None or job.task_id != task.id or job.project_id != project_id:
                    raise ConflictError("RESULT_HISTORY_MISSING", "生成历史缺失，无法完整归档")
                files = []
                archive_id = new_id("archive")
                try:
                    outputs = (("output", result.video_url), ("preview", result.preview_url))
                    for role, url in outputs:
                        if not url:
                            continue
                        source = self._source(project_id, url)
                        logical_filename = Path(unquote(urlsplit(url).path)).name
                        filename = (
                            result.metadata.get("originalFilename", logical_filename)
                            if url == result.video_url else "preview.png"
                            if "/shared/" in url else logical_filename
                        )
                        if self.file_library is None:
                            stored_fields = self.storage.copy(source)
                        else:
                            source_ref = uow.files.get_reference(
                                "project", project_id, "result", result.id,
                                "output" if url == result.video_url else "preview",
                            )
                            stored = self.file_library.import_path(
                                uow, source, scope_kind="archive", scope_id=archive_id,
                                owner_kind="result", owner_id=result.id, slot=role,
                                expected_hash=source_ref.sha256 if source_ref else None,
                                original_filename=filename,
                                mime_type=result.metadata.get("contentType")
                                if url == result.video_url else "image/png",
                            )
                            stored_fields = {"storage": "shared", "path": stored.storage_path,
                                             "sha256": stored.sha256, "size": stored.size}
                        files.append({**stored_fields, "role": role, "filename": filename})
                except (OSError, ValueError) as exc:
                    raise ShotMillError(
                        "RESULT_ARCHIVE_FAILED", "结果归档失败，原结果已保留", 409,
                        {"resultId": result.id},
                    ) from exc
                if not files:
                    raise ConflictError("RESULT_FILE_MISSING", "生成结果没有可归档文件")
                record = ArchivedResult(
                    id=archive_id, source_result_id=result.id,
                    source_project_id=project.id, source_project_title=project.title,
                    source_task_id=task.id, source_task_title=task.title,
                    source_job_id=job.id, generated_at=result.created_at,
                    final_prompt=job.final_prompt_snapshot,
                    params=deepcopy(job.params_snapshot), files=files,
                    result_metadata=deepcopy(result.metadata),
                )
                archived.append(uow.archived_results.add(record))
        return archived

    def list(self, source_project_id: str | None = None) -> list[ArchivedResult]:
        with self.uow_factory() as uow:
            return uow.archived_results.list(source_project_id)

    def delete(self, archive_id: str) -> None:
        """Release only this archive's ownership, atomically with its index.

        Physical blobs (including legacy copies) remain for a separately verified
        collector. Never unlink a file that projects or other archives can share.
        Missing/damaged media must not prevent deleting the archive record.
        """
        with self.uow_factory() as uow:
            uow.reserve_write()
            if uow.archived_results.get(archive_id) is None:
                raise NotFoundError("ARCHIVE_NOT_FOUND", "归档结果不存在")
            uow.files.release_scope("archive", archive_id)
            uow.archived_results.delete(archive_id)

    def file(self, archive_id: str, index: int) -> tuple[Path, str]:
        with self.uow_factory() as uow:
            record = uow.archived_results.get(archive_id)
            if record is None or index < 0 or index >= len(record.files):
                raise NotFoundError("ARCHIVE_FILE_NOT_FOUND", "归档文件不存在")
            file = record.files[index]
            try:
                return self.file_path_in(uow, record, file), file["filename"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ConflictError("ARCHIVE_DAMAGED", "归档文件缺失或损坏") from exc
