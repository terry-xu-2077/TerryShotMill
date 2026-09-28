"""Immutable, streaming uploads; no ComfyUI or application-specific dependencies."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile


def managed_directory(root: Path, relative: str) -> Path:
    candidate = root
    for part in Path(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink() or candidate.resolve() != candidate.absolute():
            raise ValueError("Upload directory cannot contain links")
    candidate.resolve().relative_to(root)
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


async def store_upload(reader, input_root: Path, safe_name) -> dict:
    root = input_root.resolve()
    incoming = managed_directory(root, "shotmill/.incoming")
    temporary = None
    asset_id, role, filename, expected_digest = "", "", "asset.bin", ""
    size = 0
    digest = hashlib.sha256()
    try:
        async for field in reader:
            if field.name == "asset_id":
                asset_id = (await field.text()).strip()
            elif field.name == "role":
                role = (await field.text()).strip()
            elif field.name == "sha256":
                expected_digest = (await field.text()).strip().lower()
            elif field.name == "file" and field.filename:
                if temporary is not None:
                    raise ValueError("Only one file may be uploaded")
                filename = safe_name(field.filename, "asset.bin")
                descriptor, path = tempfile.mkstemp(prefix="upload-", dir=incoming)
                temporary = Path(path)
                with os.fdopen(descriptor, "wb") as target:
                    while chunk := await field.read_chunk(size=1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    target.flush()
                    os.fsync(target.fileno())
        if not asset_id or temporary is None or not size:
            raise ValueError("asset_id and a nonempty file are required")
        checksum = digest.hexdigest()
        if expected_digest and checksum != expected_digest:
            raise ValueError("Uploaded file checksum mismatch")
        directory = managed_directory(root, f"shotmill/assets/sha256/{checksum}")
        destination = directory / filename
        if destination.is_symlink() or destination.resolve() != destination.absolute():
            raise ValueError("Upload destination cannot be a link")
        try:
            # Atomically publish without replacing a file another queued job uses.
            os.link(temporary, destination)
        except FileExistsError:
            with destination.open("rb") as existing:
                existing_digest = hashlib.file_digest(existing, "sha256").hexdigest()
            if destination.stat().st_size != size or existing_digest != checksum:
                raise ValueError("Existing uploaded file is damaged; original was not overwritten")
        return {
            "assetId": asset_id, "role": role, "filename": filename,
            "relativePath": destination.relative_to(root).as_posix(),
            "sha256": checksum, "size": size,
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
