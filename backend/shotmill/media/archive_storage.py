from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class ArchiveStorage:
    """Content-addressed copies outside project directories.

    A failed database transaction may leave an unreferenced blob, but never a
    database record pointing to a partial copy. Source files are never moved.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        candidate.relative_to(self.root)
        if candidate == self.root:
            raise ValueError("Archive file path is required")
        return candidate

    @staticmethod
    def fingerprint(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def copy(self, source: Path) -> dict[str, str | int]:
        temporary: Path | None = None
        try:
            digest = hashlib.sha256()
            size = 0
            with source.open("rb") as incoming, tempfile.NamedTemporaryFile(
                dir=self.root, prefix=".pending-", delete=False
            ) as outgoing:
                temporary = Path(outgoing.name)
                while chunk := incoming.read(1024 * 1024):
                    outgoing.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            checksum = digest.hexdigest()
            if self.fingerprint(temporary) != (checksum, size):
                raise OSError("Archive copy verification failed")
            relative = f"blobs/{checksum[:2]}/{checksum}"
            destination = self.resolve(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if self.fingerprint(destination) != (checksum, size):
                    raise OSError("Existing archive content is damaged")
            else:
                os.replace(temporary, destination)
            return {"path": relative, "sha256": checksum, "size": size}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def verify(self, file: dict) -> bool:
        try:
            return self.fingerprint(self.resolve(file["path"])) == (
                file["sha256"], file["size"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False
