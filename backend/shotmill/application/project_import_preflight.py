"""Private, verified input for import; no destination database writes occur here."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from shotmill.application.project_transfer_decode import decode_project_transfer_records
from shotmill.application.project_transfer_files import validate_project_transfer_manifest
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.media.project_package import DEFAULT_LIMITS, PackageLimits, open_project_package


@dataclass(frozen=True)
class ValidatedProjectImport:
    source: ProjectTransferSource
    files: dict[str, Path]
    provider_requirements: list[dict]


@contextmanager
def preflight_project_import(
    stream: BinaryIO, *, staging_parent: Path | None = None,
    limits: PackageLimits = DEFAULT_LIMITS,
) -> Iterator[ValidatedProjectImport]:
    with open_project_package(stream, staging_parent=staging_parent, limits=limits) as package:
        decoded = decode_project_transfer_records(package.records)
        validate_project_transfer_manifest(decoded.source, set(package.files))
        yield ValidatedProjectImport(
            decoded.source, package.files, decoded.provider_requirements,
        )
