from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from shotmill.application.asset_service import _infer_media_type
from shotmill.application.file_library import FileLibrary
from shotmill.domain.entities import Asset, new_id, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.frontend_adapter.mapper import asset_preview_url
from shotmill.media.storage import safe_filename
from shotmill.media.storage import MediaStorage
from shotmill.persistence.project_documents import ProjectDocumentStore


@dataclass(frozen=True)
class ImportSelection:
    kind: Literal["asset", "result"]
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
    direct_reference: bool = False


class AssetImportService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        media: MediaStorage,
        file_library: FileLibrary,
        documents: ProjectDocumentStore,
    ):
        self.uow_factory = uow_factory
        self.media = media
        self.file_library = file_library
        self.documents = documents

    def candidates(
        self,
        project_id: str,
        source_project_id: str | None = None,
    ) -> list[dict]:
        with self.uow_factory() as uow:
            target = uow.projects.get(project_id)
            if target is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "目标项目不存在")
            items = []
            for project in uow.projects.list():
                if project.id == project_id:
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
                            "preview_url": asset_preview_url(asset, self.media),
                            "created_at": asset.created_at,
                        }
                    )
                for task in uow.tasks.list_by_project(project.id):
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
            return items

    def _source(self, uow: UnitOfWork, selection: ImportSelection) -> ImportSource:
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
                path=self.media.resolve_read(asset.project_id, asset.project_relative_path),
                filename=asset.original_filename,
                name=asset.name,
                media_type=asset.media_type,
                checksum=asset.hash,
                content_type=content_ref.mime_type if content_ref else None,
                width=asset.width,
                height=asset.height,
                duration=asset.duration,
                thumbnail=(
                    self.media.resolve_read(asset.project_id, asset.thumbnail_path)
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
                direct_reference=asset.project_relative_path.startswith("external/"),
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
            path = self._result_path(project.id, result.video_url)
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
                    self._result_path(project.id, result.preview_url)
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

    def _result_path(self, project_id: str, url: str) -> Path:
        parsed = urlsplit(url)
        prefix = f"/media/{project_id}/"
        path = unquote(parsed.path)
        if parsed.scheme or parsed.netloc or not path.startswith(prefix):
            raise ValueError("生成结果不在来源工程中")
        return self.media.resolve_read(project_id, path[len(prefix):])

    def import_sources(self, project_id: str, selections: list[ImportSelection]) -> list[Asset]:
        if not selections or len(set(selections)) != len(selections):
            raise ShotMillError("INVALID_IMPORT_SELECTION", "请选择不重复的导入项", 422)
        try:
            with self.uow_factory() as uow:
                # Serialize source deletion with target records and file references.
                uow.reserve_write()
                project = uow.projects.get(project_id)
                if project is None:
                    raise NotFoundError("PROJECT_NOT_FOUND", "目标项目不存在")
                sources = [self._source(uow, selection) for selection in selections]
                imported = []
                for source in sources:
                    asset_id = new_id("asset")
                    if source.direct_reference:
                        if not source.path.is_file() or not source.path.stat().st_size:
                            raise ValueError("Source file is empty or missing")
                        relative = f"external/asset/{asset_id}/content"
                        uow.project_paths.add(
                            project_id, relative,
                            self.documents.reference_path(project_id, source.path),
                        )
                        checksum = source.checksum
                    else:
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
                    thumbnail_path = None
                    if source.thumbnail:
                        # Retain a useful extension for the copied preview.
                        thumbnail_name = safe_filename(
                            source.thumbnail_filename or source.thumbnail.name
                        )
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
            if isinstance(exc, (OSError, ValueError)):
                raise ShotMillError("ASSET_IMPORT_FAILED", "导入失败，原始文件未改动", 409) from exc
            raise
