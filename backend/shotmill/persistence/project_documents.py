"""Plain JSON project documents; the runtime SQL index is disposable."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock

from sqlalchemy import DateTime, select
from sqlalchemy.orm import Session

from shotmill.persistence import models
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork

FORMAT = "shotmill-project"
VERSION = 2
MODEL_BY_TABLE = {
    mapper.local_table.name: mapper.class_ for mapper in models.Base.registry.mappers
}
TABLES = [table.name for table in models.Base.metadata.sorted_tables]


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
            encoding="utf-8", newline="\n", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _row(row, model) -> dict:
    return {
        prop.columns[0].name: value.isoformat()
        if isinstance(value := getattr(row, prop.key), datetime)
        else value
        for prop in model.__mapper__.column_attrs
    }


def _rows(session: Session, model, project_id: str, task_ids: set[str],
          job_ids: set[str], file_hashes: set[str]):
    if model is models.ProjectModel:
        predicate = model.id == project_id
    elif model is models.TaskPlacementModel or model is models.TaskAssetBindingModel:
        predicate = model.task_id.in_(task_ids)
    elif model is models.RuntimeControlModel:
        predicate = model.job_id.in_(job_ids)
    elif model is models.FileReferenceModel:
        predicate = (model.scope_kind == "project") & (model.scope_id == project_id)
    elif model is models.StoredFileModel:
        predicate = model.sha256.in_(file_hashes)
    elif hasattr(model, "project_id"):
        predicate = model.project_id == project_id
    else:
        raise ValueError(f"Unassigned project table: {model.__tablename__}")
    return session.scalars(select(model).where(predicate)).all()


def snapshot_project(session: Session, project_id: str) -> dict:
    tasks = session.scalars(select(models.TaskModel.id).where(
        models.TaskModel.project_id == project_id,
    )).all()
    jobs = session.scalars(select(models.JobModel.id).where(
        models.JobModel.project_id == project_id,
    )).all()
    prompt_jobs = session.scalars(select(models.PromptEnhancementJobModel.id).where(
        models.PromptEnhancementJobModel.project_id == project_id,
    )).all()
    references = session.scalars(select(models.FileReferenceModel).where(
        (models.FileReferenceModel.scope_kind == "project") &
        (models.FileReferenceModel.scope_id == project_id),
    )).all()
    table_rows = {}
    for name in TABLES:
        model = MODEL_BY_TABLE[name]
        table_rows[name] = [
            _row(row, model) for row in _rows(
                session, model, project_id, set(tasks), set(jobs) | set(prompt_jobs),
                {reference.sha256 for reference in references},
            )
        ]
    return {"format": FORMAT, "version": VERSION, "projectId": project_id,
            "tables": table_rows}


def validate_document(document: dict) -> dict:
    if (not isinstance(document, dict) or document.get("format") != FORMAT
            or document.get("version") != VERSION
            or not set(TABLES) <= set(document.get("tables", {}))
            or not (set(document["tables"]) - set(TABLES)) <=
            {"archived_results", "pending_file_cleanup"}):
        raise ValueError("工程文件格式不受支持")
    project_id = document.get("projectId")
    if (not isinstance(project_id, str) or len(document["tables"]["projects"]) != 1
            or document["tables"]["projects"][0].get("id") != project_id):
        raise ValueError("工程文件项目身份不一致")
    return document


def _decode_document(path: Path) -> dict:
    return validate_document(json.loads(path.read_text(encoding="utf-8")))


def restore_project(session: Session, document: dict) -> str:
    for name in TABLES:
        model = MODEL_BY_TABLE[name]
        for values in document["tables"][name]:
            if model is models.FileReferenceModel and values["scope_kind"] != "project":
                continue
            if model is models.StoredFileModel and session.get(model, values["sha256"]):
                continue
            fields = {}
            for prop in model.__mapper__.column_attrs:
                column = prop.columns[0]
                value = values.get(column.name, {}) if model is models.ProjectModel and column.name == "director" else values[column.name]
                fields[prop.key] = (
                    datetime.fromisoformat(value)
                    if value is not None and isinstance(column.type, DateTime) else value
                )
            session.add(model(**fields))
        session.flush()
    return document["projectId"]


class ProjectDocumentStore:
    def __init__(self, session_factory, recent_path: Path):
        self.session_factory = session_factory
        self.recent_path = recent_path
        self.paths: dict[str, Path] = {}
        self.lock = RLock()

    def load_recent(self) -> None:
        if not self.recent_path.exists():
            return
        for name in json.loads(self.recent_path.read_text(encoding="utf-8"))["paths"]:
            path = Path(name)
            if path.is_file():
                self.open(path, remember=False)

    def remember(self) -> None:
        _atomic_json(self.recent_path, {"paths": [str(path) for path in self.paths.values()]})

    def register_new(self, project_id: str, path: Path) -> None:
        path = path.expanduser().resolve()
        if path.exists() or path in self.paths.values():
            raise FileExistsError("工程文件已存在，请选择新位置")
        self.paths[project_id] = path

    def media_root(self, project_id: str) -> Path:
        path = self.paths[project_id]
        return path.with_name(f"{path.stem}.files")

    def reference_path(self, project_id: str, path: Path) -> str:
        absolute = path.expanduser().resolve(strict=True)
        try:
            return os.path.relpath(absolute, self.paths[project_id].parent)
        except ValueError:
            return str(absolute)

    def resolve_reference(self, project_id: str, source_path: str) -> Path:
        path = Path(source_path)
        if not path.is_absolute():
            path = self.paths[project_id].parent / path
        return path.resolve()

    def open(self, path: Path, *, remember: bool = True) -> str:
        path = path.expanduser().resolve(strict=True)
        document = _decode_document(path)
        project_id = document["projectId"]
        with self.lock:
            if project_id in self.paths:
                if self.paths[project_id] != path:
                    raise ValueError("已打开同一项目的另一份工程文件")
                return project_id
            with self.session_factory() as session:
                restore_project(session, document)
                session.commit()
            self.paths[project_id] = path
            if remember:
                self.remember()
        return project_id

    def save(self, session: Session) -> None:
        for project_id, path in list(self.paths.items()):
            if session.get(models.ProjectModel, project_id) is None:
                continue
            _atomic_json(path, snapshot_project(session, project_id))

    def forget_deleted(self, session: Session) -> None:
        deleted = [project_id for project_id in self.paths
                   if session.get(models.ProjectModel, project_id) is None]
        for project_id in deleted:
            del self.paths[project_id]
        if deleted:
            self.remember()


class DocumentSession(Session):
    def flush(self, objects=None) -> None:
        if self.new or self.dirty or self.deleted:
            self.info["project_changed"] = True
        super().flush(objects)

    def execute(self, statement, *args, **kwargs):
        if getattr(statement, "is_dml", False):
            self.info["project_changed"] = True
        return super().execute(statement, *args, **kwargs)


class DocumentUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session_factory, documents: ProjectDocumentStore):
        super().__init__(session_factory)
        self.documents = documents

    def __enter__(self):
        self.documents.lock.acquire()
        try:
            return super().__enter__()
        except BaseException:
            self.documents.lock.release()
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.session is not None:
                try:
                    if exc_type is None:
                        self.commit()
                    else:
                        self.session.rollback()
                finally:
                    self.session.close()
                    self.session = None
        finally:
            self.documents.lock.release()

    def commit(self) -> None:
        assert self.session is not None
        try:
            self.session.flush()
            if self.session.info.pop("project_changed", False):
                self.documents.save(self.session)
            self.session.commit()
            self.documents.forget_deleted(self.session)
        except BaseException:
            self.session.rollback()
            raise
