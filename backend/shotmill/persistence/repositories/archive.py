from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from shotmill.domain.entities import ArchivedResult
from shotmill.persistence.models import ArchivedResultModel


def _entity(model: ArchivedResultModel) -> ArchivedResult:
    return ArchivedResult(**{
        name: getattr(model, name) for name in ArchivedResult.__dataclass_fields__
    })


class SqlAlchemyArchivedResultRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, archive_id: str) -> ArchivedResult | None:
        model = self.session.get(ArchivedResultModel, archive_id)
        return _entity(model) if model else None

    def get_by_source(self, result_id: str) -> ArchivedResult | None:
        model = self.session.scalar(select(ArchivedResultModel).where(
            ArchivedResultModel.source_result_id == result_id
        ))
        return _entity(model) if model else None

    def list(self, source_project_id: str | None = None) -> list[ArchivedResult]:
        query = select(ArchivedResultModel)
        if source_project_id is not None:
            query = query.where(ArchivedResultModel.source_project_id == source_project_id)
        query = query.order_by(ArchivedResultModel.archived_at.desc(), ArchivedResultModel.id)
        return [_entity(model) for model in self.session.scalars(query)]

    def add(self, archive: ArchivedResult) -> ArchivedResult:
        self.session.add(ArchivedResultModel(**asdict(archive)))
        self.session.flush()
        return archive

    def delete(self, archive_id: str) -> None:
        model = self.session.get(ArchivedResultModel, archive_id)
        if model is not None:
            self.session.delete(model)
            self.session.flush()
