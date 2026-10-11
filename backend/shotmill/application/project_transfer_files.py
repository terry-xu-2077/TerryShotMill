"""Enumerate owned project media for verified ZIP staging; never scan whole folders."""

import re
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.legacy_paths import legacy_owner_id
from shotmill.media.project_package import _portable_path


def collect_project_transfer_files(
    uow: UnitOfWork, source: ProjectTransferSource,
    library: FileLibrary, legacy: CleanupStorage,
    *, verified_fingerprints: dict[Path, tuple[str, int]] | None = None,
) -> dict[str, Path]:
    """Keep source's transaction open until caller stages every file.

Keys remain logical project paths, including multiple aliases for one blob. The
ZIP writer deduplicates physical content. Missing history must not be omitted.
"""
    project_id = source.project.id
    files: dict[str, Path] = {}
    verified: set[str] = set()

    def add(relative: str) -> None:
        _portable_path(relative)
        if relative in files:
            return
        if relative.startswith("shared/"):
            match = re.fullmatch(r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", relative)
            reference = uow.files.get_reference(
                "project", project_id, *match.groups(),
            ) if match else None
        else:
            reference = uow.files.get_reference(
                "project", project_id, "legacy_path", legacy_owner_id(relative), "content",
            )
        if reference is not None or relative.startswith("shared/"):
            file = uow.files.get(reference.sha256) if reference else None
            if file is None:
                raise ConflictError("PROJECT_TRANSFER_MEDIA_MISSING", "项目媒体缺失或损坏。")
            if file.sha256 not in verified:
                try:
                    library.storage.verify(file)
                except OSError as exc:
                    raise ConflictError(
                        "PROJECT_TRANSFER_MEDIA_MISSING", "项目媒体缺失或损坏。",
                    ) from exc
                verified.add(file.sha256)
            path = library.storage.resolve(file)
            if verified_fingerprints is not None:
                verified_fingerprints[path] = (file.sha256, file.size)
        else:
            path = legacy.resolve(project_id, relative)
        if not path.is_file():
            raise ConflictError("PROJECT_TRANSFER_MEDIA_MISSING", "项目媒体缺失或损坏。")
        files[relative] = path

    for relative in sorted(project_transfer_media_paths(source)):
        add(relative)
    return files


def project_transfer_media_paths(source: ProjectTransferSource) -> set[str]:
    """Pure logical enumeration shared by export and import; touches no filesystem."""
    project_id = source.project.id
    files: set[str] = set()

    def add(relative: str) -> None:
        _portable_path(relative)
        files.add(relative)

    def add_url(url: str) -> None:
        prefix = f"/media/{project_id}/"
        if not url.startswith(prefix):
            raise ConflictError("PROJECT_TRANSFER_MEDIA_INVALID", "结果不属于当前项目媒体目录。")
        add(url[len(prefix):])

    assets = {asset.id: asset for asset in source.assets}
    for asset in source.assets:
        add(asset.project_relative_path)
        if asset.thumbnail_path:
            add(asset.thumbnail_path)
    for result in source.results:
        add_url(result.video_url)
        if result.preview_url:
            add_url(result.preview_url)
    for job in source.jobs:
        for media in (
            *job.assets_snapshot, *job.context_snapshot.get("media", []),
            *(job.execution_context or {}).get("media", []),
        ):
            add(media["projectRelativePath"])
    for job in source.prompt_jobs:
        for media in (*job.source_snapshot.get("media", []),
                      *job.context_snapshot.get("media", [])):
            if media.get("projectRelativePath"):
                add(media["projectRelativePath"])
            else:
                asset = assets.get(media["assetId"])
                if asset is None:
                    raise ConflictError(
                        "PROJECT_TRANSFER_HISTORY_MEDIA_MISSING", "增强历史引用的素材已缺失。",
                    )
                add(asset.project_relative_path)
    for revision in source.prompt_revisions:
        historical_assets = {
            media["assetId"]
            for job in source.prompt_jobs if job.revision_id == revision.id
            for media in (*job.source_snapshot.get("media", []),
                          *job.context_snapshot.get("media", []))
            if media.get("projectRelativePath") in files and "assetId" in media
        }
        if any(asset_id not in assets and asset_id not in historical_assets
               for asset_id in revision.asset_ids):
            raise ConflictError(
                "PROJECT_TRANSFER_HISTORY_MEDIA_MISSING",
                "增强版本的历史素材已缺失，无法完整导出。",
            )
    return files


def validate_project_transfer_manifest(source: ProjectTransferSource, paths: set[str]) -> None:
    if project_transfer_media_paths(source) != paths:
        raise ConflictError(
            "PROJECT_TRANSFER_MANIFEST_MISMATCH", "项目记录与包内文件清单不一致。",
        )
