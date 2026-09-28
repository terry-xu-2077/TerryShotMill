from datetime import UTC, datetime

import pytest
from alembic import command
from shotmill.domain.entities import ArchivedResult, Project, Task
from shotmill.persistence.database import create_database_engine
from shotmill.persistence.migrations import alembic_config, upgrade_database
from shotmill.persistence.models import ProjectModel
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from sqlalchemy import delete, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker


def archive_record(archive_id="a"):
    return ArchivedResult(
        id=archive_id, source_result_id="result", source_project_id="p",
        source_project_title="Original project", source_task_id="t",
        source_task_title="Original task", source_job_id="job",
        generated_at=datetime(2026, 9, 27, tzinfo=UTC), final_prompt="original prompt",
        params={"seed": 42, "resolution": [1280, 720]},
        files=[{"path": "a/video.mp4", "sha256": "checksum", "size": 8}],
        result_metadata={"duration": 5},
    )


def test_archive_survives_source_deletion_and_database_reopen(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'archive.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    factory = sessionmaker(engine)
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.projects.add(Project(id="p", title="Original project"))
        uow.tasks.add(Task(id="t", project_id="p", title="Original task", display_order=1))
        uow.archived_results.add(archive_record())
    with engine.begin() as connection:
        connection.execute(delete(ProjectModel).where(ProjectModel.id == "p"))
    engine.dispose()
    engine = create_database_engine(url)
    with SqlAlchemyUnitOfWork(sessionmaker(engine)) as uow:
        assert uow.projects.get("p") is None
        assert uow.tasks.get("t") is None
        record = uow.archived_results.get("a")
        assert record.source_project_title == "Original project"
        assert record.source_task_title == "Original task"
        assert record.final_prompt == "original prompt"
        assert record.params == {"seed": 42, "resolution": [1280, 720]}
        assert record.files == archive_record().files
        assert record.result_metadata == {"duration": 5}
        assert record.generated_at.date().isoformat() == "2026-09-27"
        assert uow.archived_results.get_by_source("result").id == "a"
        assert len(uow.archived_results.list("p")) == 1
        assert uow.archived_results.list("other") == []
    engine.dispose()


def test_archive_uniqueness_and_transaction_rollback(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'unique.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    factory = sessionmaker(engine)
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.archived_results.add(archive_record())
    with pytest.raises(IntegrityError), SqlAlchemyUnitOfWork(factory) as uow:
        uow.archived_results.add(archive_record("duplicate"))
    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(factory) as uow:
        record = archive_record("rolled-back")
        record.source_result_id = "other-result"
        uow.archived_results.add(record)
        raise RuntimeError("injected failure")
    with SqlAlchemyUnitOfWork(factory) as uow:
        assert [item.id for item in uow.archived_results.list()] == ["a"]
        assert uow.archived_results.get("rolled-back") is None
        assert uow.archived_results.get_by_source("unknown") is None
    engine.dispose()


def test_archive_migration_upgrade_and_downgrade(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
    command.upgrade(alembic_config(url), "0008")
    engine = create_database_engine(url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO projects
            (id, title, description, use_description_for_ai_prompt, created_at, updated_at)
            VALUES ('p', 'Keep me', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
    upgrade_database(url)
    assert inspect(engine).get_foreign_keys("archived_results") == []
    with SqlAlchemyUnitOfWork(sessionmaker(engine)) as uow:
        assert uow.projects.get("p").title == "Keep me"
        uow.archived_results.add(archive_record())
    command.downgrade(alembic_config(url), "0008")
    assert "archived_results" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        title = connection.execute(text("SELECT title FROM projects WHERE id = 'p'")).scalar_one()
        assert title == "Keep me"
    engine.dispose()
