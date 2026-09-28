"""Immutable content-addressed bytes. Logical names and ownership live in the database."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO

from shotmill.domain.files import StoredFile
from shotmill.media.cleanup_storage import CleanupStorage

CHUNK_SIZE = 1024 * 1024


class FileStorage:
    def __init__(self, files_root: Path):
        # This root belongs to the application, never to an individual project.
        self.managed = CleanupStorage(files_root)

    @staticmethod
    def relative_path(sha256: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("Invalid file content identity")
        return f"objects/{sha256[:2]}/{sha256}"

    def resolve(self, file: StoredFile) -> Path:
        if file.storage_path != self.relative_path(file.sha256):
            raise ValueError("File path does not match content identity")
        return self.managed.resolve("objects", f"{file.sha256[:2]}/{file.sha256}")

    def verify(self, file: StoredFile) -> None:
        path = self.resolve(file)
        with path.open("rb") as stream:
            if (os.fstat(stream.fileno()).st_size != file.size
                    or hashlib.file_digest(stream, "sha256").hexdigest() != file.sha256):
                raise OSError("Existing shared file is damaged")

    def put(
        self, source: BinaryIO, *, expected_hash: str | None = None,
    ) -> StoredFile:
        if expected_hash is not None:
            self.relative_path(expected_hash)
        directory = self.managed.resolve("staging")
        directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=".pending-", delete=False,
            ) as output:
                temporary = Path(output.name)
                digest, size = hashlib.sha256(), 0
                while chunk := source.read(CHUNK_SIZE):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            checksum = digest.hexdigest()
            if expected_hash is not None and checksum != expected_hash:
                raise ValueError("Imported file checksum mismatch")
            file = StoredFile(checksum, size, self.relative_path(checksum))
            destination = self.resolve(file)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Link the owned temporary file, never a different project's source.
                # Atomic no-overwrite publication; unlinking the temp leaves one file.
                os.link(temporary, destination)
            except FileExistsError:
                self.verify(file)
            return file
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
