"""Unpack a project ZIP beside a user-selected ordinary project file."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from shotmill.application.file_library import FileLibrary
from shotmill.application.project_package_media import bind_imported_paths, media_paths
from shotmill.errors import ConflictError, ShotMillError
from shotmill.media.project_package import open_project_package
from shotmill.persistence.project_documents import (
    ProjectDocumentStore, _atomic_json, validate_document,
)


@dataclass(frozen=True)
class ProjectImportOutcome:
    project_id: str
    provider_requirements: list[dict]


class ProjectImportService:
    def __init__(self, library: FileLibrary, documents: ProjectDocumentStore):
        self.library = library
        self.documents = documents

    def import_package(self, stream: BinaryIO, destination: Path) -> ProjectImportOutcome:
        destination = destination.expanduser().resolve()
        if destination.suffix.lower() != ".shotmill" or not destination.parent.is_dir():
            raise ShotMillError(
                "PROJECT_IMPORT_DESTINATION_INVALID",
                "请选择已存在目录中的 .shotmill 工程文件位置", 422,
            )
        media_root = destination.with_name(f"{destination.stem}.files")
        if destination.exists() or media_root.exists():
            raise FileExistsError("目标工程文件或素材目录已存在")
        staging = self.library.storage.managed.resolve("staging")
        staging.mkdir(parents=True, exist_ok=True)
        with open_project_package(stream, staging_parent=staging) as package:
            document = validate_document(package.document)
            project_id = document["projectId"]
            if project_id in self.documents.paths:
                raise ConflictError(
                    "PROJECT_ALREADY_OPEN", "该项目已经打开；请在独立环境中导入这份工程包",
                )
            expected = {f"project.files/{path}" for path in media_paths(document)}
            expected.update(f"library/{row['sha256']}"
                            for row in document["tables"]["stored_files"])
            if set(package.files) != expected:
                raise ValueError("项目记录与包内文件清单不一致")
            imported = bind_imported_paths(document, destination.stem)
            for task in imported["tables"]["generation_tasks"]:
                task["generation_configuration_required"] = True
            with tempfile.TemporaryDirectory(
                prefix="shotmill-unpack-", dir=destination.parent,
            ) as temporary:
                unpacked = Path(temporary) / "project.files"
                unpacked.mkdir()
                for name, source in package.files.items():
                    if name.startswith("project.files/"):
                        target = unpacked / name[len("project.files/"):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
                    else:
                        with source.open("rb") as incoming:
                            self.library.storage.put(
                                incoming, expected_hash=name.removeprefix("library/"),
                            )
                os.replace(unpacked, media_root)
                _atomic_json(destination, imported)
            self.documents.open(destination)
            return ProjectImportOutcome(
                project_id, document["tables"]["projects"][0]["transfer_requirements"],
            )
