import mimetypes
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shotmill.application.file_library import FileLibrary
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError
from shotmill.media.storage import MediaStorage
from shotmill.persistence.project_documents import ProjectDocumentStore


@dataclass(frozen=True)
class ReadableProjectFile:
    path: Path
    filename: str
    mime_type: str


class ProjectFileReader:
    def __init__(
        self, factory: Callable[[], UnitOfWork], library: FileLibrary,
        media: MediaStorage, documents: ProjectDocumentStore,
    ):
        self.factory = factory
        self.library = library
        self.media = media
        self.documents = documents

    def read(
        self, project_id: str, relative: str, *, require_exists: bool = True,
    ) -> ReadableProjectFile:
        with self.factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在")
            external = re.fullmatch(r"external/asset/([A-Za-z0-9_-]+)/content", relative)
            if external:
                source = uow.project_paths.get(project_id, relative)
                if source is None:
                    raise NotFoundError("MEDIA_NOT_FOUND", "媒体引用不存在")
                path = self.documents.resolve_reference(project_id, source)
                if require_exists and not path.is_file():
                    raise NotFoundError("MEDIA_NOT_FOUND", "原始素材文件不存在")
                return ReadableProjectFile(
                    path, path.name,
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
            match = re.fullmatch(
                r"shared/([a-z_]+)/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", relative,
            )
            if match is None:
                if relative.startswith("shared/"):
                    raise NotFoundError("MEDIA_NOT_FOUND", "媒体引用不存在")
                try:
                    path = self.media.resolve(project_id, relative)
                except ValueError as exc:
                    raise NotFoundError("MEDIA_NOT_FOUND", "媒体引用不存在") from exc
                if require_exists and not path.is_file():
                    raise NotFoundError("MEDIA_NOT_FOUND", "媒体文件不存在")
                return ReadableProjectFile(
                    path, path.name,
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
            reference = uow.files.get_reference("project", project_id, *match.groups())
            if reference is None:
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
