import hashlib
import os
import tempfile
from pathlib import Path

from shotmill.media.archive_storage import ArchiveStorage
from shotmill.media.cleanup_storage import CleanupStorage


class ImportStorage:
    def __init__(self, projects_root: Path):
        self.managed = CleanupStorage(projects_root)

    def copy(
        self,
        source: Path,
        project_id: str,
        relative: str,
        *,
        expected_hash: str | None = None,
    ) -> str:
        destination = self.managed.resolve(project_id, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            digest = hashlib.sha256()
            size = 0
            with (
                source.open("rb") as incoming,
                tempfile.NamedTemporaryFile(
                    dir=destination.parent, prefix=".import-", delete=False
                ) as outgoing,
            ):
                temporary = Path(outgoing.name)
                while chunk := incoming.read(1024 * 1024):
                    outgoing.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            checksum = digest.hexdigest()
            if not size:
                raise ValueError("Source file is empty")
            if expected_hash and checksum != expected_hash:
                raise ValueError("Source checksum does not match")
            if ArchiveStorage.fingerprint(temporary) != (checksum, size):
                raise OSError("Imported copy verification failed")
            # The destination is a fresh asset ID; refuse accidental overwrites.
            if destination.exists():
                raise FileExistsError(destination)
            temporary.rename(destination)
            return checksum
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
