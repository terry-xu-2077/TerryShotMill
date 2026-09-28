"""Rebind verified staged media to independent destination owners in one UoW."""

import mimetypes
from copy import deepcopy
from pathlib import Path, PurePosixPath

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_transfer_identity import RemappedProjectIdentity
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.domain.files import FileReference, StoredFile
from shotmill.domain.repositories import UnitOfWork


def bind_project_import_media(
    uow: UnitOfWork, library: FileLibrary, identity: RemappedProjectIdentity,
    staged_files: dict[str, Path],
) -> ProjectTransferSource:
    """Caller owns reserved transaction and persists returned graph before commit.

Only pass files from preflight_project_import. Their filenames are verified SHA256
identities. Database failure may leave immutable orphan bytes, never delete them.
"""
    source = deepcopy(identity.source)
    project_id = source.project.id
    blobs: dict[Path, StoredFile] = {}

    def bind(relative, kind, owner, slot, filename=None, mime=None):
        staged = staged_files[relative]
        file = blobs.get(staged)
        if file is None:
            file = uow.files.get(staged.name)
            if file is not None:
                library.storage.verify(file)
            else:
                with staged.open("rb") as stream:
                    file = library.storage.put(stream, expected_hash=staged.name)
                uow.files.register(file)
            blobs[staged] = file
        filename = filename or PurePosixPath(relative).name
        uow.files.bind(FileReference(
            "project", project_id, kind, owner, slot, file.sha256,
            filename, mime or mimetypes.guess_type(filename)[0],
        ))
        return f"shared/{kind}/{owner}/{slot}", file.sha256

    # Preserve old relative paths for legacy prompt jobs that only stored IDs.
    old_assets = {asset.id: deepcopy(asset) for asset in source.assets}
    for asset in source.assets:
        asset.project_relative_path, asset.hash = bind(
            asset.project_relative_path, "asset", asset.id, "content", asset.original_filename,
        )
        if asset.thumbnail_path:
            asset.thumbnail_path, _ = bind(
                asset.thumbnail_path, "asset", asset.id, "preview", "preview.png", "image/png",
            )
    old_prefix = f"/media/{identity.original_project_id}/"
    for result in source.results:
        old_output, old_preview = result.video_url, result.preview_url
        relative = old_output.removeprefix(old_prefix)
        output, _ = bind(
            relative, "result", result.id, "output", result.metadata.get("originalFilename"),
            result.metadata.get("contentType"),
        )
        result.video_url = f"/media/{project_id}/{output}"
        if old_preview == old_output:
            result.preview_url = result.video_url
        elif old_preview:
            preview, _ = bind(
                old_preview.removeprefix(old_prefix), "result", result.id, "preview",
                "preview.png", "image/png",
            )
            result.preview_url = f"/media/{project_id}/{preview}"

    def media(items, kind, owner, prefix):
        for index, item in enumerate(items):
            if not item.get("projectRelativePath"):
                asset = old_assets[item["assetId"]]
                item.update(projectRelativePath=asset.project_relative_path,
                            originalFilename=asset.original_filename, mediaType=asset.media_type)
            item["projectRelativePath"], _ = bind(
                item["projectRelativePath"], kind, owner, f"{prefix}-{index}",
                item.get("originalFilename"),
            )

    for job in source.jobs:
        media(job.assets_snapshot, "job", job.id, "input")
        media(job.context_snapshot.get("media", []), "job", job.id, "context")
        media((job.execution_context or {}).get("media", []), "job", job.id, "execution")
    for job in source.prompt_jobs:
        media(job.source_snapshot.get("media", []), "prompt_job", job.id, "input")
        media(job.context_snapshot.get("media", []), "prompt_job", job.id, "context")
    return source
