"""Build a private, complete project ZIP before exposing it to a download caller."""

import os
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_transfer_files import collect_project_transfer_files
from shotmill.application.project_transfer_records import serialize_project_transfer_records
from shotmill.application.project_transfer_source import read_project_transfer_source
from shotmill.application.project_transfer_validation import validate_project_transfer_graph
from shotmill.domain.repositories import UnitOfWork
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.export_lease import export_lease
from shotmill.media.project_package import DEFAULT_LIMITS, PackageLimits, write_project_package


class ProjectExportService:
    def __init__(
        self, factory: Callable[[], UnitOfWork], library: FileLibrary, projects_root: Path,
    ):
        self.factory = factory
        self.library = library
        self.legacy = CleanupStorage(projects_root)

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
                source = read_project_transfer_source(uow, project_id)
                acquired = ownership.enter_context(export_lease(Path(directory) / "owner.lock",
                                                                create=True))
                if not acquired:
                    raise OSError("Could not acquire private export lease")
                validate_project_transfer_graph(source)
                records = serialize_project_transfer_records(source)
                for requirement in uow.projects.get_transfer_requirements(project_id):
                    if requirement not in records["providerRequirements"]:
                        records["providerRequirements"].append(requirement)
                files = collect_project_transfer_files(uow, source, self.library, self.legacy)
                with path.open("xb") as output:
                    write_project_package(output, records, files, limits=limits)
                    output.flush()
                    os.fsync(output.fileno())
            # Caller must finish streaming before leaving this context. No source
            # transaction is held while a slow client downloads the completed ZIP.
            yield path
