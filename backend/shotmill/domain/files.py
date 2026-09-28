"""Application-wide physical objects and scoped logical references."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredFile:
    sha256: str
    size: int
    storage_path: str


@dataclass(frozen=True)
class FileReference:
    scope_kind: str
    scope_id: str
    owner_kind: str
    owner_id: str
    slot: str
    sha256: str
    original_filename: str | None = None
    mime_type: str | None = None


class FileRepository(Protocol):
    def get_reference(
        self, scope_kind: str, scope_id: str, owner_kind: str, owner_id: str, slot: str,
    ) -> FileReference | None: ...
    def get(self, sha256: str) -> StoredFile | None: ...
    def register(self, file: StoredFile) -> StoredFile: ...
    def bind(self, reference: FileReference) -> None: ...
    def references(self, sha256: str) -> list[FileReference]: ...
    def release_owner(
        self, scope_kind: str, scope_id: str, owner_kind: str, owner_id: str,
    ) -> None: ...
    def unreferenced(self) -> list[StoredFile]: ...
    def delete_unreferenced(self, sha256: str) -> None: ...
    def release_scope(self, scope_kind: str, scope_id: str) -> None: ...
