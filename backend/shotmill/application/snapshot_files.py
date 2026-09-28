"""Give newly admitted immutable jobs their own references to shared input bytes."""

import re
from copy import deepcopy

from shotmill.domain.files import FileReference
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError
from shotmill.media.legacy_paths import legacy_owner_id


def shared_history_owners(
    uow: UnitOfWork, project_id: str, *, excluding_tasks: frozenset[str] = frozenset(),
) -> set[tuple[str, str]]:
    """Retain aliases used by older snapshots until explicit migration is complete."""
    owners = set()
    for task in uow.tasks.list_by_project(project_id):
        if task.id in excluding_tasks:
            continue
        media = []
        for job in uow.jobs.list_by_task(task.id):
            media.extend(job.assets_snapshot)
            media.extend(job.context_snapshot.get("media", []))
            media.extend((job.execution_context or {}).get("media", []))
        for job in uow.prompt_jobs.list_by_task(task.id):
            media.extend(job.source_snapshot.get("media", []))
            media.extend(job.context_snapshot.get("media", []))
        for item in media:
            path = item.get("projectRelativePath")
            if isinstance(path, str):
                match = re.fullmatch(
                    r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", path,
                )
                if match:
                    owners.add((match[1], match[2]))
    return owners


def capture_prompt_media(uow: UnitOfWork, project_id: str, media: list[dict]) -> list[dict]:
    frozen = deepcopy(media)
    for item in frozen:
        asset = uow.assets.get(item["assetId"])
        if asset is not None and asset.project_id == project_id:
            item.update({
                "projectRelativePath": asset.project_relative_path,
                "originalFilename": asset.original_filename,
                "mediaType": asset.media_type,
            })
        # Missing/foreign assets keep the established per-job execution error.
    return frozen


def release_unused_shared_aliases(uow: UnitOfWork, project_id: str, paths: set[str]) -> None:
    """Release deleted owners retained solely for histories that no longer exist."""
    protected = shared_history_owners(uow, project_id)
    repositories = {"asset": uow.assets, "result": uow.results,
                    "job": uow.jobs, "prompt_job": uow.prompt_jobs}
    candidates = set()
    for path in paths:
        match = re.fullmatch(r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", path)
        if match:
            candidates.add((match[1], match[2]))
    for kind, owner_id in candidates - protected:
        repository = repositories.get(kind)
        if repository is not None and repository.get(owner_id) is None:
            uow.files.release_owner("project", project_id, kind, owner_id)


def freeze_media_references(
    uow: UnitOfWork, project_id: str, owner_kind: str, owner_id: str, media: list[dict],
    *, slot_prefix: str = "input",
) -> list[dict]:
    frozen = deepcopy(media)
    for index, item in enumerate(frozen):
        path = item.get("projectRelativePath", "")
        if not isinstance(path, str) or not path:
            continue
        if path.startswith("shared/"):
            match = re.fullmatch(r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", path)
            reference = (
                uow.files.get_reference("project", project_id, *match.groups()) if match else None
            )
        else:
            reference = uow.files.get_reference(
                "project", project_id, "legacy_path", legacy_owner_id(path), "content",
            )
            if reference is None:
                continue  # Unmigrated media retains its historical path.
        if reference is None:
            raise ConflictError("GENERATION_ASSET_FILE_MISSING", "素材引用已失效，请重新检查。")
        slot = f"{slot_prefix}-{index}"
        uow.files.bind(FileReference(
            "project", project_id, owner_kind, owner_id, slot, reference.sha256,
            reference.original_filename, reference.mime_type,
        ))
        item["projectRelativePath"] = f"shared/{owner_kind}/{owner_id}/{slot}"
    return frozen
