import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.legacy_paths import legacy_owner_id


@dataclass(frozen=True)
class ReadableProjectFile:
    path: Path
    filename: str
    mime_type: str


class ProjectFileReader:
    def __init__(
        self, factory: Callable[[], UnitOfWork], library: FileLibrary,
        legacy: CleanupStorage | None = None,
    ):
        self.factory = factory
        self.library = library
        self.legacy = legacy

    def read(
        self, project_id: str, relative: str, *, require_exists: bool = True,
    ) -> ReadableProjectFile:
        match = re.fullmatch(r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", relative)
        legacy_path = None
        if match is None:
            if relative.startswith("shared/") or self.legacy is None:
                raise NotFoundError("MEDIA_NOT_FOUND", "媒体引用不存在")
            try:
                owner = ("legacy_path", legacy_owner_id(relative), "content")
                legacy_path = self.legacy.resolve(project_id, relative)
            except ValueError as exc:
                raise NotFoundError("MEDIA_NOT_FOUND", "媒体引用不存在") from exc
        else:
            owner = match.groups()
        with self.factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在")
            reference = uow.files.get_reference("project", project_id, *owner)
            if reference is None:
                if legacy_path is not None:
                    if require_exists and not legacy_path.is_file():
                        raise NotFoundError("MEDIA_NOT_FOUND", "媒体文件不存在")
                    mime = mimetypes.guess_type(relative)[0] or "application/octet-stream"
                    return ReadableProjectFile(legacy_path, legacy_path.name, mime)
                raise NotFoundError("MEDIA_NOT_FOUND", "媒体引用不存在")
            file = uow.files.get(reference.sha256)
            if file is None:
                raise NotFoundError("MEDIA_NOT_FOUND", "媒体文件不存在")
            path = self.library.storage.resolve(file)
            if require_exists and not path.is_file():
                raise NotFoundError("MEDIA_NOT_FOUND", "媒体文件不存在")
            filename = reference.original_filename or "file.bin"
            mime = reference.mime_type or mimetypes.guess_type(filename)[0]
            return ReadableProjectFile(path, filename, mime or "application/octet-stream")

    def resolve(self, project_id: str, relative: str) -> Path:
        # Like legacy MediaStorage.resolve: the caller owns missing-file semantics.
        # Ownership is still checked before returning any physical path.
        return self.read(project_id, relative, require_exists=False).path
