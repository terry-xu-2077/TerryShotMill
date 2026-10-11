from __future__ import annotations

import hashlib
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.application.legacy_file_references import release_unused_legacy_paths
from shotmill.application.snapshot_files import shared_history_owners
from shotmill.domain.entities import Asset, new_id, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.media.storage import MediaStorage
from shotmill.persistence.project_documents import ProjectDocumentStore


def _infer_media_type(content_type: str | None, filename: str) -> str:
    if content_type:
        prefix = content_type.split("/", 1)[0].lower()
        if prefix in {"image", "video", "audio"}:
            return prefix
    suffix = Path(filename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        return "image"
    if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
        return "video"
    if suffix in {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg"}:
        return "audio"
    return "other"


class AssetService:
    def __init__(
        self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage,
        file_library: FileLibrary, documents: ProjectDocumentStore | None = None,
    ) -> None:
        self.uow_factory = uow_factory
        self.storage = storage
        self.file_library = file_library
        self.documents = documents

    def import_path(
        self, project_id: str, path: Path, *, name: str | None = None,
        category: str = "reference", tags: list[str] | None = None,
    ) -> Asset:
        if self.documents is None:
            raise RuntimeError("Project document storage is required for local files")
        try:
            source = path.expanduser().resolve(strict=True)
            if not source.is_file() or not source.stat().st_size:
                raise ValueError("原始素材文件为空或不是文件")
            with source.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        except (OSError, ValueError) as exc:
            raise ShotMillError("MEDIA_NOT_FOUND", "原始素材文件无法读取", 422) from exc
        now = utcnow()
        asset_id = new_id("asset")
        logical = f"external/asset/{asset_id}/content"
        asset = Asset(
            id=asset_id, project_id=project_id,
            name=(name or source.stem).strip() or source.name,
            original_filename=source.name, project_relative_path=logical,
            media_type=_infer_media_type(None, source.name),
            category=category.strip() or "reference",
            tags=[item.strip() for item in (tags or []) if item.strip()],
            hash=checksum, created_at=now, updated_at=now,
        )
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            uow.project_paths.add(
                project_id, logical, self.documents.reference_path(project_id, source),
            )
            uow.assets.add(asset)
            project.updated_at = now
            uow.projects.update(project)
        return asset

    def import_bytes(
        self,
        project_id: str,
        filename: str,
        content: bytes,
        *,
        content_type: str | None = None,
        name: str | None = None,
        category: str = "reference",
        tags: list[str] | None = None,
    ) -> Asset:
        if not content:
            raise ShotMillError("ASSET_EMPTY", "Asset file is empty", 422)
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")

        asset_id = new_id("asset")
        now = utcnow()
        asset = Asset(
            id=asset_id,
            project_id=project_id,
            name=(name or Path(filename).stem or filename).strip(),
            original_filename=Path(filename).name,
            project_relative_path=f"shared/asset/{asset_id}/content",
            media_type=_infer_media_type(content_type, filename),
            category=category.strip() or "reference",
            tags=[item.strip() for item in (tags or []) if item.strip()],
            hash=None,
            created_at=now,
            updated_at=now,
        )
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            file = self.file_library.import_file(
                uow, BytesIO(content), scope_kind="project", scope_id=project_id,
                owner_kind="asset", owner_id=asset_id, slot="content",
                original_filename=asset.original_filename, mime_type=content_type,
            )
            asset.hash = file.sha256
            uow.assets.add(asset)
            project.updated_at = now
            uow.projects.update(project)
        return asset

    def update(
        self,
        project_id: str,
        asset_id: str,
        *,
        name: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> Asset:
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            asset = uow.assets.get(asset_id)
            if asset is None or asset.project_id != project_id:
                raise NotFoundError("ASSET_NOT_FOUND", "Asset not found")
            if name is not None:
                clean = name.strip()
                if not clean:
                    raise ShotMillError("ASSET_NAME_REQUIRED", "Asset name is required", 422)
                asset.name = clean
            if category is not None:
                asset.category = category.strip() or "reference"
            if tags is not None:
                asset.tags = [item.strip() for item in tags if item.strip()]
            asset.updated_at = utcnow()
            uow.assets.update(asset)
            return asset

    def delete(self, project_id: str, asset_id: str) -> None:
        with self.uow_factory() as uow:
            uow.reserve_write()
            asset = uow.assets.get(asset_id)
            if asset is None or asset.project_id != project_id:
                raise NotFoundError("ASSET_NOT_FOUND", "Asset not found")
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            if project is not None and project.cover_asset_id == asset_id:
                raise ConflictError(
                    "ASSET_IS_PROJECT_COVER", "该图片用作项目封面，请先更换封面或恢复自动封面。"
                )
            # A draft enhancement can freeze media that is not yet in Task bindings.
            # Preserve its asset record as well as the underlying immutable file.
            active_media = [
                media
                for job in uow.jobs.list_active() if job.project_id == project_id
                for media in job.assets_snapshot
            ] + [
                media
                for job in uow.prompt_jobs.list_active() if job.project_id == project_id
                for media in job.source_snapshot.get("media", [])
            ]
            if any(media.get("assetId") == asset_id for media in active_media):
                raise ConflictError(
                    "ASSET_IN_ACTIVE_JOB",
                    "素材正被排队或执行中的任务使用，请等待完成或取消后再删除。",
                )
            count = uow.assets.binding_count(asset_id)
            if count:
                raise ConflictError(
                    "ASSET_IN_USE",
                    "Asset is referenced by one or more tasks",
                    {"bindingCount": count},
                )
            historical = shared_history_owners(uow, project_id)
            uow.assets.delete(asset_id)
            if ("asset", asset_id) not in historical:
                uow.files.release_owner("project", project_id, "asset", asset_id)
            release_unused_legacy_paths(
                uow, project_id, {asset.project_relative_path, asset.thumbnail_path or ""},
            )
        # Keep the underlying file for historical immutable Job snapshots.
        # A future storage GC may remove unreferenced files after retention checks.
