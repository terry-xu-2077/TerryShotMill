from dataclasses import asdict

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from shotmill.domain.entities import PendingFileCleanup
from shotmill.persistence.models import PendingFileCleanupModel


class SqlAlchemyCleanupRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self) -> list[PendingFileCleanup]:
        rows = self.session.scalars(select(PendingFileCleanupModel).order_by(
            PendingFileCleanupModel.created_at, PendingFileCleanupModel.id
        ))
        return [PendingFileCleanup(**{
            key: getattr(row, key) for key in PendingFileCleanup.__dataclass_fields__
        }) for row in rows]

    def add(self, item: PendingFileCleanup) -> None:
        self.session.add(PendingFileCleanupModel(**asdict(item)))
        self.session.flush()

    def fail(self, cleanup_id: str, message: str) -> None:
        self.session.execute(update(PendingFileCleanupModel).where(
            PendingFileCleanupModel.id == cleanup_id
        ).values(last_error=message))

    def delete(self, cleanup_id: str) -> None:
        self.session.execute(delete(PendingFileCleanupModel).where(
            PendingFileCleanupModel.id == cleanup_id
        ))
