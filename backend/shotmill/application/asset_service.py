from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shotmill.domain.entities import Asset, new_id, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.media.storage import MediaStorage


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
    def __init__(self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage) -> None:
        self.uow_factory = uow_factory
        self.storage = storage

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
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")

        asset_id = new_id("asset")
        relative_path, checksum = self.storage.write_asset(project_id, asset_id, filename, content)
        now = utcnow()
        asset = Asset(
            id=asset_id,
            project_id=project_id,
            name=(name or Path(filename).stem or filename).strip(),
            original_filename=Path(filename).name,
            project_relative_path=relative_path,
            media_type=_infer_media_type(content_type, filename),
            category=category.strip() or "reference",
            tags=[item.strip() for item in (tags or []) if item.strip()],
            hash=checksum,
            created_at=now,
            updated_at=now,
        )
        try:
            with self.uow_factory() as uow:
                uow.assets.add(asset)
                project = uow.projects.get(project_id)
                if project is not None:
                    project.updated_at = now
                    uow.projects.update(project)
        except Exception:
            path = self.storage.resolve(project_id, relative_path)
            path.unlink(missing_ok=True)
            raise
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
            asset = uow.assets.get(asset_id)
            if asset is None or asset.project_id != project_id:
                raise NotFoundError("ASSET_NOT_FOUND", "Asset not found")
            project = uow.projects.get(project_id)
            if project is not None and project.cover_asset_id == asset_id:
                raise ConflictError(
                    "ASSET_IS_PROJECT_COVER", "该图片用作项目封面，请先更换封面或恢复自动封面。"
                )
            count = uow.assets.binding_count(asset_id)
            if count:
                raise ConflictError(
                    "ASSET_IN_USE",
                    "Asset is referenced by one or more tasks",
                    {"bindingCount": count},
                )
            relative_path = asset.project_relative_path
            uow.assets.delete(asset_id)
        # Keep the underlying file for historical immutable Job snapshots.
        # A future storage GC may remove unreferenced files after retention checks.
        _ = relative_path
