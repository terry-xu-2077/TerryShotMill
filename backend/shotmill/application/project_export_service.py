"""Build a private, complete project ZIP before exposing it to a download caller."""

import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_package_media import collect_package_files
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError
from shotmill.media.export_lease import export_lease
from shotmill.media.project_package import DEFAULT_LIMITS, PackageLimits, write_project_package
from shotmill.media.storage import MediaStorage
from shotmill.persistence.project_documents import ProjectDocumentStore, _decode_document


class ProjectExportService:
    def __init__(
        self, factory: Callable[[], UnitOfWork], library: FileLibrary,
        documents: ProjectDocumentStore, media: MediaStorage,
    ):
        self.factory = factory
        self.library = library
        self.documents = documents
        self.media = media

    def recover_abandoned(self) -> int:
        """Only marked, inactive exports; serialize creation/recovery using the DB lock."""
        removed = 0
        with self.factory() as uow:
            uow.reserve_write()
            managed = self.library.storage.managed
            staging = managed.resolve("staging")
            if not staging.is_dir():
                return 0
            for candidate in staging.iterdir():
                if not re.fullmatch(r"project-export-[a-zA-Z0-9_-]{8,}", candidate.name):
                    continue
                try:
                    directory = managed.resolve("staging", candidate.name)
                    if not directory.is_dir():
                        continue
                    names = {item.name for item in directory.iterdir()}
                    if "owner.lock" not in names or not names <= {"owner.lock", "project.zip"}:
                        continue
                    lease = managed.resolve("staging", f"{candidate.name}/owner.lock")
                    package = managed.resolve("staging", f"{candidate.name}/project.zip")
                    with export_lease(lease) as acquired:
                        if not acquired:
                            continue
                        package.unlink(missing_ok=True)
                    lease.unlink()
                    directory.rmdir()
                    removed += 1
                except (OSError, ValueError):
                    # Busy, linked, unknown or inaccessible content is preserved.
                    continue
        return removed

    @contextmanager
    def prepare(
        self, project_id: str, *, limits: PackageLimits = DEFAULT_LIMITS,
    ) -> Iterator[Path]:
        staging = self.library.storage.managed.resolve("staging")
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="project-export-", dir=staging) as directory, (
            ExitStack()
        ) as ownership:
            path = Path(directory) / "project.zip"
            # Keep deletion, edits and submissions outside the snapshot boundary
            # until all referenced bytes have been copied into the private ZIP.
            with self.factory() as uow:
                if uow.projects.get(project_id) is None or project_id not in self.documents.paths:
                    raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在")
                acquired = ownership.enter_context(export_lease(Path(directory) / "owner.lock",
                                                                create=True))
                if not acquired:
                    raise OSError("Could not acquire private export lease")
                document, files = collect_package_files(
                    _decode_document(self.documents.paths[project_id]),
                    self.documents, self.media, self.library,
                )
                with path.open("xb") as output:
                    write_project_package(output, document, files, limits=limits)
                    output.flush()
                    os.fsync(output.fileno())
            # Caller must finish streaming before leaving this context. No source
            # transaction is held while a slow client downloads the completed ZIP.
            yield path
