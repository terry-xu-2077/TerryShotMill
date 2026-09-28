"""Transactional bridge between business-owned file references and global immutable bytes."""

from pathlib import Path
from typing import BinaryIO

from shotmill.domain.files import FileReference, StoredFile
from shotmill.domain.repositories import UnitOfWork
from shotmill.media.file_storage import FileStorage


class FileLibrary:
    def __init__(self, storage: FileStorage):
        self.storage = storage

    def import_file(
        self, uow: UnitOfWork, source: BinaryIO, *, scope_kind: str, scope_id: str,
        owner_kind: str, owner_id: str, slot: str, expected_hash: str | None = None,
        original_filename: str | None = None, mime_type: str | None = None,
    ) -> StoredFile:
        """Caller reserves a write transaction before this and saves the owner in it.

        A rollback may leave an unregistered immutable object, never a visible
        reference to missing bytes. Do not unlink on rollback: another owner may
        already depend on the same object. Crash recovery/GC is a separate gate.
        """
        file = self.storage.put(source, expected_hash=expected_hash)
        uow.files.register(file)
        uow.files.bind(FileReference(
            scope_kind, scope_id, owner_kind, owner_id, slot, file.sha256,
            original_filename, mime_type,
        ))
        return file

    def resolve(self, uow: UnitOfWork, reference: FileReference) -> Path:
        file = uow.files.get(reference.sha256)
        if file is None or reference not in uow.files.references(reference.sha256):
            raise ValueError("File does not belong to this logical owner")
        return self.storage.resolve(file)

    def import_path(
        self, uow: UnitOfWork, source: Path, *, scope_kind: str, scope_id: str,
        owner_kind: str, owner_id: str, slot: str, expected_hash: str | None = None,
        original_filename: str | None = None, mime_type: str | None = None,
    ) -> StoredFile:
        """Reuse verified managed bytes; outside/legacy sources must be independently read."""
        file = uow.files.get(expected_hash) if expected_hash else None
        if file is not None and source == self.storage.resolve(file):
            self.storage.verify(file)
            uow.files.bind(FileReference(
                scope_kind, scope_id, owner_kind, owner_id, slot, file.sha256,
                original_filename, mime_type,
            ))
            return file
        with source.open("rb") as stream:
            return self.import_file(
                uow, stream, scope_kind=scope_kind, scope_id=scope_id,
                owner_kind=owner_kind, owner_id=owner_id, slot=slot,
                expected_hash=expected_hash, original_filename=original_filename,
                mime_type=mime_type,
            )
