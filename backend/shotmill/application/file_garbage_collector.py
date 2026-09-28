"""Explicit collection of registered, unreferenced global objects; not scheduled yet."""

from collections.abc import Callable

from shotmill.application.file_reference_audit import audit_file_references
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError
from shotmill.media.file_storage import FileStorage


class FileGarbageCollector:
    def __init__(self, factory: Callable[[], UnitOfWork], storage: FileStorage):
        self.factory = factory
        self.storage = storage

    def collect_registered(self) -> int:
        # Result collection publishes bytes before its final database transaction.
        # Its job remains active throughout that interval. Do not collect while
        # any video job can be collecting/reusing an otherwise unreferenced blob.
        with self.factory() as uow:
            uow.reserve_write()
            if uow.jobs.list_active():
                raise ConflictError("FILE_COLLECTION_BUSY", "生成任务未结束，暂不能清理文件。")
            candidates = uow.files.unreferenced()
            audit_file_references(uow, {file.sha256 for file in candidates})
            removed = 0
            for file in candidates:
                path = self.storage.resolve(file)
                if path.exists():
                    self.storage.verify(file)
                    path.unlink()
                # If interruption followed unlink, the row survives rollback.
                # A retry removes that missing, still-unreferenced registration.
                uow.files.delete_unreferenced(file.sha256)
                removed += 1
            return removed
