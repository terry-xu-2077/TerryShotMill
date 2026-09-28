from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from shotmill.application.asset_service import _infer_media_type
from shotmill.application.file_library import FileLibrary
from shotmill.application.lifecycle_service import require_writable
from shotmill.application.result_archive_service import ResultArchiveService
from shotmill.domain.entities import Asset, PendingFileCleanup, new_id, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.frontend_adapter.mapper import asset_preview_url
from shotmill.media.import_storage import ImportStorage
from shotmill.media.storage import safe_filename


@dataclass(frozen=True)
class ImportSelection:
    kind: Literal["asset", "result", "archive"]
    id: str


@dataclass
class ImportSource:
    path: Path
    filename: str
    name: str
    media_type: str
    provenance: dict
    checksum: str | None = None
    content_type: str | None = None
    thumbnail: Path | None = None
    thumbnail_filename: str | None = None
    thumbnail_content_type: str | None = None
    thumbnail_checksum: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    category: str = "reference"
    tags: list[str] = field(default_factory=list)


class AssetImportService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        archive: ResultArchiveService,
        storage: ImportStorage,
        file_library: FileLibrary | None = None,
    ):
        self.uow_factory = uow_factory
        self.archive = archive
        self.storage = storage
        self.file_library = file_library

    def candidates(
        self,
        project_id: str,
        source_project_id: str | None = None,
    ) -> list[dict]:
        with self.uow_factory() as uow:
            target = uow.projects.get(project_id)
            if target is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "目标项目不存在")
            require_writable(target)
            items = []
            for project in uow.projects.list():
                if project.id == project_id or project.deleted_at is not None:
                    continue
                if source_project_id is not None and project.id != source_project_id:
                    continue
                for asset in uow.assets.list_by_project(project.id):
                    items.append(
                        {
                            "kind": "asset",
                            "id": asset.id,
                            "name": asset.name,
                            "source_project_id": project.id,
                            "source_project_title": project.title,
                            "media_type": asset.media_type,
                            "preview_url": asset_preview_url(asset, self.archive.media),
                            "created_at": asset.created_at,
                        }
                    )
                for task in uow.tasks.list_by_project(project.id):
                    if task.deleted_at is not None:
                        continue
                    for result in uow.results.list_by_task(task.id):
                        items.append(
                            {
                                "kind": "result",
                                "id": result.id,
                                "name": task.title,
                                "source_project_id": project.id,
                                "source_project_title": project.title,
                                "media_type": _infer_media_type(
                                    result.metadata.get("contentType"), result.video_url
                                ),
                                "preview_url": result.preview_url,
                                "created_at": result.created_at,
                            }
                        )
            for record in uow.archived_results.list(source_project_id):
                output = next((f for f in record.files if f["role"] == "output"), None)
                if output is None:
                    continue
                preview_index = next(
                    (i for i, f in enumerate(record.files) if f["role"] == "preview"), None
                )
                items.append(
                    {
                        "kind": "archive",
                        "id": record.id,
                        "name": record.source_task_title,
                        "source_project_id": record.source_project_id,
                        "source_project_title": record.source_project_title,
                        "media_type": _infer_media_type(
                            record.result_metadata.get("contentType"), output["filename"]
                        ),
                        "preview_url": (
                            f"/api/v1/result-archive/{record.id}/files/{preview_index}"
                            if preview_index is not None
                            else None
                        ),
                        "created_at": record.generated_at,
                    }
                )
            return items

    def _source(self, uow: UnitOfWork, selection: ImportSelection) -> ImportSource:
        if selection.kind == "archive":
            record = uow.archived_results.get(selection.id)
            if record is None:
                raise NotFoundError("ARCHIVE_NOT_FOUND", "归档结果不存在")
            output = next((file for file in record.files if file["role"] == "output"), None)
            if output is None or not self.archive.verify_in(uow, record):
                raise ConflictError("ARCHIVE_DAMAGED", "归档文件缺失或损坏，无法导入")
            preview = next((file for file in record.files if file["role"] == "preview"), None)
            return ImportSource(
                path=self.archive.file_path_in(uow, record, output),
                filename=output["filename"],
                name=record.source_task_title,
                checksum=output["sha256"],
                media_type=_infer_media_type(
                    record.result_metadata.get("contentType"), output["filename"]
                ),
                provenance={
                    "sourceType": "archive",
                    "sourceId": record.id,
                    "projectId": record.source_project_id,
                    "projectTitle": record.source_project_title,
                    "taskId": record.source_task_id,
                    "taskTitle": record.source_task_title,
                    "resultId": record.source_result_id,
                    "jobId": record.source_job_id,
                    "generatedAt": record.generated_at.isoformat(),
                    "prompt": record.final_prompt,
                    "params": deepcopy(record.params),
                },
                thumbnail=self.archive.file_path_in(uow, record, preview) if preview else None,
                thumbnail_filename=preview["filename"] if preview else None,
                thumbnail_checksum=preview["sha256"] if preview else None,
                duration=record.result_metadata.get("durationSeconds"),
                width=record.result_metadata.get("width"),
                height=record.result_metadata.get("height"),
            )
        if selection.kind == "asset":
            asset = uow.assets.get(selection.id)
            if asset is None:
                raise NotFoundError("ASSET_NOT_FOUND", "来源资产不存在")
            project = uow.projects.get(asset.project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "来源项目不存在")
            content_ref = uow.files.get_reference("project", asset.project_id, "asset", asset.id,
                                                  "content")
            preview_ref = uow.files.get_reference("project", asset.project_id, "asset", asset.id,
                                                  "preview")
            return ImportSource(
                path=self.archive.media.resolve_read(asset.project_id, asset.project_relative_path),
                filename=asset.original_filename,
                name=asset.name,
                media_type=asset.media_type,
                checksum=asset.hash,
                content_type=content_ref.mime_type if content_ref else None,
                width=asset.width,
                height=asset.height,
                duration=asset.duration,
                thumbnail=(
                    self.archive.media.resolve_read(asset.project_id, asset.thumbnail_path)
                    if asset.thumbnail_path
                    else None
                ),
                thumbnail_filename=(
                    preview_ref.original_filename if preview_ref else
                    Path(asset.thumbnail_path).name if asset.thumbnail_path else None
                ),
                thumbnail_content_type=preview_ref.mime_type if preview_ref else None,
                thumbnail_checksum=preview_ref.sha256 if preview_ref else None,
                category=asset.category,
                tags=list(asset.tags),
                provenance={
                    "sourceType": "asset",
                    "sourceId": asset.id,
                    "projectId": project.id,
                    "projectTitle": project.title,
                    "assetName": asset.name,
                    "originalSource": deepcopy(asset.provenance),
                },
            )
        if selection.kind == "result":
            result = uow.results.get(selection.id)
            if result is None:
                raise NotFoundError("RESULT_NOT_FOUND", "来源生成结果不存在")
            project = uow.projects.get(result.project_id)
            task = uow.tasks.get(result.task_id)
            job = uow.jobs.get(result.job_id)
            if project is None or task is None or job is None:
                raise ConflictError("RESULT_HISTORY_MISSING", "生成历史不完整，无法导入")
            path = self.archive._source(project.id, result.video_url)
            filename = result.metadata.get(
                "originalFilename", Path(unquote(urlsplit(result.video_url).path)).name,
            )
            return ImportSource(
                path=path,
                filename=filename,
                name=task.title,
                media_type=_infer_media_type(result.metadata.get("contentType"), filename),
                content_type=result.metadata.get("contentType"),
                provenance={
                    "sourceType": "result",
                    "sourceId": result.id,
                    "projectId": project.id,
                    "projectTitle": project.title,
                    "taskId": task.id,
                    "taskTitle": task.title,
                    "jobId": job.id,
                    "generatedAt": result.created_at.isoformat(),
                    "prompt": job.final_prompt_snapshot,
                    "params": deepcopy(job.params_snapshot),
                },
                thumbnail=(
                    self.archive._source(project.id, result.preview_url)
                    if result.preview_url
                    else None
                ),
                thumbnail_filename=(
                    filename if result.preview_url == result.video_url else "preview.png"
                    if result.preview_url and "/shared/" in result.preview_url else
                    Path(unquote(urlsplit(result.preview_url).path)).name
                    if result.preview_url else None
                ),
                duration=result.metadata.get("durationSeconds"),
                width=result.metadata.get("width"),
                height=result.metadata.get("height"),
            )
        raise ShotMillError("INVALID_IMPORT_SOURCE", "不支持的导入来源", 422)

    def import_sources(self, project_id: str, selections: list[ImportSelection]) -> list[Asset]:
        if not selections or len(set(selections)) != len(selections):
            raise ShotMillError("INVALID_IMPORT_SELECTION", "请选择不重复的导入项", 422)
        staged_paths = []
        try:
            with self.uow_factory() as uow:
                # Serialize source deletion with target records and file references.
                uow.reserve_write()
                project = uow.projects.get(project_id)
                if project is None:
                    raise NotFoundError("PROJECT_NOT_FOUND", "目标项目不存在")
                require_writable(project)
                sources = [self._source(uow, selection) for selection in selections]
                imported = []
                for source in sources:
                    asset_id = new_id("asset")
                    if self.file_library is not None:
                        relative = f"shared/asset/{asset_id}/content"
                        file = self.file_library.import_path(
                            uow, source.path, scope_kind="project", scope_id=project_id,
                            owner_kind="asset", owner_id=asset_id, slot="content",
                            expected_hash=source.checksum, original_filename=source.filename,
                            mime_type=source.content_type,
                        )
                        if not file.size:
                            raise ValueError("Source file is empty")
                        checksum = file.sha256
                    else:
                        relative = f"assets/{asset_id}_{safe_filename(source.filename)}"
                        staged_paths.append(relative)
                        checksum = self.storage.copy(
                            source.path, project_id, relative, expected_hash=source.checksum,
                        )
                    thumbnail_path = None
                    if source.thumbnail:
                        # Retain a useful extension even when an archive blob has a hash-only name.
                        thumbnail_name = safe_filename(
                            source.thumbnail_filename or source.thumbnail.name
                        )
                        if self.file_library is not None:
                            thumbnail_path = f"shared/asset/{asset_id}/preview"
                            preview_file = self.file_library.import_path(
                                uow, source.thumbnail, scope_kind="project", scope_id=project_id,
                                owner_kind="asset", owner_id=asset_id, slot="preview",
                                original_filename=thumbnail_name,
                                mime_type=source.thumbnail_content_type,
                                expected_hash=source.thumbnail_checksum,
                            )
                            if not preview_file.size:
                                raise ValueError("Source preview is empty")
                        else:
                            thumbnail_path = f"thumbnails/{asset_id}_{thumbnail_name}"
                            staged_paths.append(thumbnail_path)
                            self.storage.copy(source.thumbnail, project_id, thumbnail_path)
                    asset = Asset(
                        id=asset_id,
                        project_id=project_id,
                        name=source.name,
                        original_filename=source.filename,
                        project_relative_path=relative,
                        media_type=source.media_type,
                        category=source.category,
                        tags=source.tags,
                        width=source.width,
                        height=source.height,
                        duration=source.duration,
                        hash=checksum,
                        thumbnail_path=thumbnail_path,
                        provenance={**source.provenance, "importedAt": utcnow().isoformat()},
                    )
                    imported.append(uow.assets.add(asset))
                project.updated_at = utcnow()
                uow.projects.update(project)
            return imported
        except Exception as exc:
            if staged_paths:
                # Records have rolled back. Track copied files for safe, restartable cleanup.
                with self.uow_factory() as cleanup:
                    cleanup.reserve_write()
                    cleanup.cleanup.add(
                        PendingFileCleanup(new_id("cleanup"), project_id, staged_paths)
                    )
            if isinstance(exc, (OSError, ValueError)):
                raise ShotMillError("ASSET_IMPORT_FAILED", "导入失败，原始文件未改动", 409) from exc
            raise
