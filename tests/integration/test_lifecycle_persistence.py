from datetime import UTC, datetime

from alembic import command
from shotmill.domain.entities import Project, Task
from shotmill.persistence.database import create_database_engine
from shotmill.persistence.migrations import alembic_config, upgrade_database
from shotmill.persistence.repositories.project_asset import SqlAlchemyProjectRepository
from shotmill.persistence.repositories.task import SqlAlchemyTaskRepository
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_archive_survives_trash_restore_and_reopening_database(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'lifecycle.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    timestamp = datetime(2026, 9, 27, tzinfo=UTC)
    with Session(engine) as session:
        projects = SqlAlchemyProjectRepository(session)
        tasks = SqlAlchemyTaskRepository(session)
        projects.add(Project(id="p", title="Project", archived_at=timestamp))
        tasks.add(Task(id="t", project_id="p", display_order=1, title="Task"))
        session.commit()
    with Session(engine) as session:
        projects = SqlAlchemyProjectRepository(session)
        tasks = SqlAlchemyTaskRepository(session)
        project = projects.get("p")
        task = tasks.get("t")
        assert project.archived_at is not None
        assert task.archived_at is None
        task.archived_at = timestamp
        task.deleted_at = timestamp
        project.deleted_at = timestamp
        projects.update(project)
        tasks.update(task)
        session.commit()
    engine.dispose()
    engine = create_database_engine(url)
    with Session(engine) as session:
        projects = SqlAlchemyProjectRepository(session)
        tasks = SqlAlchemyTaskRepository(session)
        project = projects.get("p")
        task = tasks.get("t")
        assert task.deleted_at is not None
        assert project.deleted_at is not None
        project.deleted_at = None
        projects.update(project)
        session.commit()
    with Session(engine) as session:
        project = SqlAlchemyProjectRepository(session).get("p")
        task = SqlAlchemyTaskRepository(session).get("t")
        assert project.deleted_at is None
        assert project.archived_at is not None
        assert task.deleted_at is not None
        task.deleted_at = None
        SqlAlchemyTaskRepository(session).update(task)
        session.commit()
    with Session(engine) as session:
        task = SqlAlchemyTaskRepository(session).get("t")
        assert task.deleted_at is None
        assert task.archived_at is not None
        assert task.display_order == 1
    engine.dispose()


def test_lifecycle_migration_preserves_existing_project(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    command.upgrade(alembic_config(url), "0007")
    engine = create_database_engine(url)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO projects (id, title, description, use_description_for_ai_prompt, "
            "created_at, updated_at) VALUES "
            "('existing', 'Original', '', 0, '2026-09-27', '2026-09-27')"
        ))
    upgrade_database(url)
    with Session(engine) as session:
        project = SqlAlchemyProjectRepository(session).get("existing")
        assert project.title == "Original"
        assert project.archived_at is None
        assert project.deleted_at is None
    engine.dispose()
