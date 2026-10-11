"""Paths to files owned by the user, recorded without copying their bytes."""

from sqlalchemy.orm import Session

from shotmill.persistence.models import ProjectFilePathModel


class ProjectPathRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, project_id: str, logical_path: str) -> str | None:
        row = self.session.get(ProjectFilePathModel, (project_id, logical_path))
        return row.source_path if row else None

    def add(self, project_id: str, logical_path: str, source_path: str) -> None:
        self.session.add(ProjectFilePathModel(
            project_id=project_id, logical_path=logical_path, source_path=source_path,
        ))
        self.session.flush()
