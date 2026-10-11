import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shotmill.domain.files import FileReference, StoredFile
from shotmill.persistence.models import FileReferenceModel, StoredFileModel


def _file(row: StoredFileModel) -> StoredFile:
    return StoredFile(row.sha256, row.size, row.storage_path)


def _reference(row: FileReferenceModel) -> FileReference:
    return FileReference(
        row.scope_kind, row.scope_id, row.owner_kind, row.owner_id, row.slot, row.sha256,
        row.original_filename, row.mime_type,
    )


class SqlAlchemyFileRepository:
    """Mutations participate in the caller's reserved write transaction."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, sha256: str) -> StoredFile | None:
        row = self.session.get(StoredFileModel, sha256)
        return _file(row) if row else None

    def get_reference(
        self, scope_kind: str, scope_id: str, owner_kind: str, owner_id: str, slot: str,
    ) -> FileReference | None:
        identity = (scope_kind, scope_id, owner_kind, owner_id, slot)
        row = self.session.get(FileReferenceModel, identity)
        return _reference(row) if row else None

    def register(self, file: StoredFile) -> StoredFile:
        if (not re.fullmatch(r"[0-9a-f]{64}", file.sha256)
                or type(file.size) is not int or file.size < 0
                or file.storage_path != f"objects/{file.sha256[:2]}/{file.sha256}"):
            raise ValueError("Invalid stored file identity")
        existing = self.get(file.sha256)
        if existing is not None:
            if existing != file:
                raise ValueError("Conflicting immutable file metadata")
            return existing
        self.session.add(StoredFileModel(
            sha256=file.sha256, size=file.size, storage_path=file.storage_path,
        ))
        self.session.flush()
        return file

    def bind(self, reference: FileReference) -> None:
        identity = (reference.scope_kind, reference.scope_id, reference.owner_kind,
                    reference.owner_id, reference.slot)
        for value, limit in zip(identity, (32, 80, 32, 80, 240), strict=True):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError("Invalid logical file owner")
        if reference.scope_kind != "project":
            raise ValueError("Unknown file reference scope")
        if self.get(reference.sha256) is None:
            raise ValueError("Cannot reference an unregistered file")
        existing = self.session.get(FileReferenceModel, identity)
        if existing is not None:
            if _reference(existing) != reference:
                raise ValueError("Cannot overwrite an immutable file reference")
            return
        self.session.add(FileReferenceModel(
            scope_kind=reference.scope_kind, scope_id=reference.scope_id,
            owner_kind=reference.owner_kind, owner_id=reference.owner_id,
            slot=reference.slot, sha256=reference.sha256,
            original_filename=reference.original_filename, mime_type=reference.mime_type,
        ))
        self.session.flush()

    def references(self, sha256: str) -> list[FileReference]:
        rows = self.session.scalars(
            select(FileReferenceModel).where(FileReferenceModel.sha256 == sha256)
            .order_by(FileReferenceModel.scope_kind, FileReferenceModel.scope_id,
                      FileReferenceModel.owner_kind, FileReferenceModel.owner_id,
                      FileReferenceModel.slot)
        )
        return [_reference(row) for row in rows]

    def release_owner(
        self, scope_kind: str, scope_id: str, owner_kind: str, owner_id: str,
    ) -> None:
        self.session.execute(delete(FileReferenceModel).where(
            FileReferenceModel.scope_kind == scope_kind,
            FileReferenceModel.scope_id == scope_id,
            FileReferenceModel.owner_kind == owner_kind,
            FileReferenceModel.owner_id == owner_id,
        ))
        self.session.flush()

    def unreferenced(self) -> list[StoredFile]:
        # This is a diagnostic candidate list, not authorization to delete bytes.
        referenced = select(FileReferenceModel.sha256).where(
            FileReferenceModel.sha256 == StoredFileModel.sha256,
        ).exists()
        return [_file(row) for row in self.session.scalars(
            select(StoredFileModel).where(~referenced).order_by(StoredFileModel.sha256),
        )]

    def release_scope(self, scope_kind: str, scope_id: str) -> None:
        if scope_kind != "project" or not scope_id:
            raise ValueError("An exact file reference scope is required")
        self.session.execute(delete(FileReferenceModel).where(
            FileReferenceModel.scope_kind == scope_kind,
            FileReferenceModel.scope_id == scope_id,
        ))
        self.session.flush()

    def delete_unreferenced(self, sha256: str) -> None:
        if self.references(sha256):
            raise ValueError("Cannot remove a referenced file registration")
        self.session.execute(delete(StoredFileModel).where(StoredFileModel.sha256 == sha256))
        self.session.flush()
