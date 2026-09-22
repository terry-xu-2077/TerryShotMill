from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from shotmill.persistence.repositories.history import (
    SqlAlchemyContextRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyPromptEnhancementBatchRepository,
    SqlAlchemyPromptEnhancementJobRepository,
    SqlAlchemyPromptRevisionRepository,
    SqlAlchemyResultRepository,
)
from shotmill.persistence.repositories.project_asset import (
    SqlAlchemyAssetRepository,
    SqlAlchemyProjectRepository,
)
from shotmill.persistence.repositories.runtime_control import SqlAlchemyRuntimeControlRepository
from shotmill.persistence.repositories.task import SqlAlchemyTaskRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self.session_factory()
        self.runtime_controls = SqlAlchemyRuntimeControlRepository(self.session)
        self.projects = SqlAlchemyProjectRepository(self.session)
        self.assets = SqlAlchemyAssetRepository(self.session)
        self.tasks = SqlAlchemyTaskRepository(self.session)
        self.jobs = SqlAlchemyJobRepository(self.session)
        self.results = SqlAlchemyResultRepository(self.session)
        self.prompt_revisions = SqlAlchemyPromptRevisionRepository(self.session)
        self.prompt_batches = SqlAlchemyPromptEnhancementBatchRepository(self.session)
        self.prompt_jobs = SqlAlchemyPromptEnhancementJobRepository(self.session)
        self.contexts = SqlAlchemyContextRepository(self.session)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.session is None:
            return
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None

    def commit(self) -> None:
        assert self.session is not None
        self.session.commit()

    def rollback(self) -> None:
        assert self.session is not None
        self.session.rollback()


UnitOfWorkFactory = Callable[[], SqlAlchemyUnitOfWork]
