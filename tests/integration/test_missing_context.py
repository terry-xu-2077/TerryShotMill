import asyncio

import pytest
from alembic import command
from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationService
from shotmill.application.task_service import TaskService
from shotmill.application.workspace_query import WorkspaceQuery
from shotmill.domain.entities import ContextLink, Project, Task
from shotmill.errors import ConflictError
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.migrations import alembic_config, upgrade_database
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from sqlalchemy import text


@pytest.fixture
def missing_context(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'context.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)

    def factory():
        return SqlAlchemyUnitOfWork(sessions)

    with factory() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        for index, name in enumerate(["earlier", "source", "target"]):
            uow.tasks.add(Task(
                id=name, project_id="p", title=name, display_order=index + 1,
                final_prompt="prompt", generation_params={"contextMode": "尾帧承接"},
            ))
        uow.contexts.replace_for_target("target", [
            ContextLink("link", "p", "source", "target", "visual", "result")
        ])
    yield factory, MediaStorage(tmp_path / "projects"), url
    engine.dispose()


def test_missing_link_survives_source_deletion_and_blocks_fallback(missing_context):
    factory, storage, _ = missing_context
    with factory() as uow:
        uow.tasks.delete("source")
    with factory() as uow:
        link = uow.contexts.list_by_target("target")[0]
        assert link.source_deleted_at is not None
        assert link.source_task_title == "source"
        assert link.source_task_id == "source"
        assert link.source_result_id == "result"
    summary = WorkspaceQuery(factory, storage).task_summary("p", "target")
    assert summary.missing_references[0].source_task_title == "source"
    assert "永久删除" in summary.generation_warnings[0]
    service = GenerationService(factory, None, storage, ProjectEventBus())
    with pytest.raises(ConflictError) as error:
        asyncio.run(service.validate_task("p", "target"))
    assert error.value.code == "CONTEXT_SOURCE_DELETED"


def test_regular_context_save_does_not_silently_rebind(missing_context):
    factory, storage, _ = missing_context
    with factory() as uow:
        uow.tasks.delete("source")
    service = TaskService(factory, storage)
    with factory() as uow:
        target = uow.tasks.get("target")
        service._replace_context(uow, target, uow.tasks.get("earlier"))
        assert uow.contexts.list_by_target("target")[0].source_task_id == "source"
        target.generation_params["contextMode"] = "不承接"
        service._replace_context(uow, target, uow.tasks.get("earlier"))
        assert uow.contexts.list_by_target("target") == []


def test_target_deletion_removes_owned_links_and_downgrade_protects_history(missing_context):
    factory, _, url = missing_context
    with factory() as uow:
        uow.tasks.delete("source")
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(alembic_config(url), "0009")
    # Later revisions may already have downgraded before revision 0010 refuses
    # to discard tombstones. Restore the current schema before using current ORM.
    upgrade_database(url)
    with factory() as uow:
        assert uow.contexts.list_by_target("target")[0].source_deleted_at is not None
        uow.tasks.delete("target")
    with factory() as uow:
        assert uow.contexts.list_by_target("target") == []
    command.downgrade(alembic_config(url), "0009")
    upgrade_database(url)


def test_migration_preserves_existing_context_links(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    with SqlAlchemyUnitOfWork(sessions) as uow:
        uow.projects.add(Project(id="p", title="Project"))
        for index, name in enumerate(["source", "target"]):
            uow.tasks.add(Task(id=name, project_id="p", title=name, display_order=index + 1))
        uow.contexts.replace_for_target("target", [
            ContextLink("old-link", "p", "source", "target", "visual", "old-result", True)
        ])
    command.downgrade(alembic_config(url), "0009")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM generation_context_links")) == 1
    upgrade_database(url)
    with SqlAlchemyUnitOfWork(sessions) as uow:
        link = uow.contexts.list_by_target("target")[0]
        assert link.id == "old-link"
        assert link.source_result_id == "old-result"
        assert link.stale is True
        assert link.source_deleted_at is None
        assert link.source_task_title is None
    engine.dispose()
