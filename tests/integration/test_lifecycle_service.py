import asyncio

import pytest
from shotmill.application.asset_service import AssetService
from shotmill.application.batch_service import BatchProductionService
from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationService
from shotmill.application.lifecycle_service import LifecycleService, require_writable
from shotmill.application.result_service import ResultService
from shotmill.application.task_service import SaveTaskData, TaskService
from shotmill.domain.entities import (
    ContextLink,
    Job,
    Project,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Task,
)
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError, NotFoundError
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.migrations import upgrade_database
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork


@pytest.fixture
def lifecycle(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'lifecycle.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)

    def factory():
        return SqlAlchemyUnitOfWork(sessions)

    with factory() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        for index in range(2):
            uow.tasks.add(Task(id=f"t{index}", project_id="p", display_order=index, title="Task"))
    yield LifecycleService(factory), factory
    engine.dispose()


def test_task_restore_preserves_archive_and_read_only(lifecycle):
    service, factory = lifecycle
    service.transition_tasks("p", ["t0"], "archive")
    service.transition_tasks("p", ["t0"], "trash")
    service.transition_tasks("p", ["t0"], "restore")
    with factory() as uow:
        task = uow.tasks.get("t0")
        assert task.archived_at is not None
        assert task.deleted_at is None
        with pytest.raises(ConflictError):
            require_writable(uow.projects.get("p"), task)
    service.transition_tasks("p", ["t0"], "unarchive")
    with factory() as uow:
        require_writable(uow.projects.get("p"), uow.tasks.get("t0"))


def test_batch_failure_does_not_partially_archive(lifecycle):
    service, factory = lifecycle
    service.transition_tasks("p", ["t1"], "trash")
    with pytest.raises(ConflictError):
        service.transition_tasks("p", ["t0", "t1"], "archive")
    with factory() as uow:
        assert uow.tasks.get("t0").archived_at is None
    with pytest.raises(NotFoundError):
        service.transition_tasks("p", ["t0", "missing"], "trash")
    with factory() as uow:
        assert uow.tasks.get("t0").deleted_at is None


def test_project_restore_does_not_restore_trashed_children(lifecycle):
    service, factory = lifecycle
    service.transition_tasks("p", ["t0"], "trash")
    service.transition_project("p", "archive")
    with pytest.raises(ConflictError):
        service.transition_tasks("p", ["t0"], "restore")
    service.transition_project("p", "trash")
    service.transition_project("p", "restore")
    with factory() as uow:
        assert uow.projects.get("p").archived_at is not None
        assert uow.tasks.get("t0").deleted_at is not None


@pytest.mark.parametrize("project_archived", [False, True])
@pytest.mark.parametrize("child_actions", [[], ["archive"], ["trash"], ["archive", "trash"]])
def test_project_restore_preserves_exact_child_lifecycle(
    lifecycle, project_archived, child_actions
):
    service, factory = lifecycle
    for action in child_actions:
        service.transition_tasks("p", ["t0"], action)
    with factory() as uow:
        child = uow.tasks.get("t0")
        before = (child.archived_at, child.deleted_at, child.updated_at)
    if project_archived:
        service.transition_project("p", "archive")
    with factory() as uow:
        project_archive_time = uow.projects.get("p").archived_at
    service.transition_project("p", "trash")
    # A fresh service reads the persisted state, not an in-memory restore snapshot.
    LifecycleService(factory).transition_project("p", "restore")
    with factory() as uow:
        project = uow.projects.get("p")
        child = uow.tasks.get("t0")
        assert project.deleted_at is None
        assert project.archived_at == project_archive_time
        assert (child.archived_at, child.deleted_at, child.updated_at) == before
        unaffected = uow.tasks.get("t1")
        assert unaffected.archived_at is None and unaffected.deleted_at is None


def test_archived_task_cannot_be_edited(lifecycle):
    service, factory = lifecycle
    service.transition_tasks("p", ["t0"], "archive")
    with pytest.raises(ConflictError):
        TaskService(factory).update("p", "t0", SaveTaskData(title="Changed"))
    with factory() as uow:
        assert uow.tasks.get("t0").title == "Task"


def test_archived_project_rejects_new_tasks_and_reordering(lifecycle):
    service, factory = lifecycle
    service.transition_project("p", "archive")
    tasks = TaskService(factory)
    with pytest.raises(ConflictError):
        tasks.create("p", SaveTaskData(title="New"))
    with pytest.raises(ConflictError):
        tasks.reorder("p", ["t1", "t0"])
    with factory() as uow:
        assert [task.id for task in uow.tasks.list_by_project("p")] == ["t0", "t1"]


@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("target", ["project", "task"])
def test_inactive_objects_cannot_submit_video(lifecycle, providers, tmp_path, action, target):
    service, factory = lifecycle
    if target == "project":
        service.transition_project("p", action)
    else:
        service.transition_tasks("p", ["t0"], action)
    generation = GenerationService(
        factory, providers[1], MediaStorage(tmp_path / "media"), ProjectEventBus()
    )
    with pytest.raises(ConflictError) as error:
        asyncio.run(generation.submit("p", "t0"))
    assert error.value.code == "OBJECT_READ_ONLY"
    with factory() as uow:
        assert uow.jobs.list_by_task("t0") == []
    assert providers[1].requests == []


def test_deletion_impact_excludes_internal_batch_dependencies(lifecycle):
    service, factory = lifecycle
    with factory() as uow:
        uow.contexts.replace_for_target("t1", [ContextLink(
            id="link", project_id="p", source_task_id="t0", target_task_id="t1",
            kind="visual", source_result_id="result-original",
        )])
    impacts = service.deletion_impacts("p", ["t0"])
    assert len(impacts) == 1
    assert impacts[0].target_task_id == "t1"
    assert impacts[0].source_result_id == "result-original"
    assert service.deletion_impacts("p", ["t0", "t1"]) == []
    service.transition_tasks("p", ["t1"], "trash")
    assert service.deletion_impacts("p", ["t0"]) == impacts
    with factory() as uow:
        assert uow.contexts.list_by_target("t1")[0].source_task_id == "t0"


def test_archived_project_assets_remain_readable_but_cannot_change(lifecycle, tmp_path):
    service, factory = lifecycle
    assets = AssetService(factory, MediaStorage(tmp_path / "media"))
    asset = assets.import_bytes("p", "reference.txt", b"original")
    service.transition_project("p", "archive")
    with pytest.raises(ConflictError):
        assets.import_bytes("p", "new.txt", b"new")
    with pytest.raises(ConflictError):
        assets.update("p", asset.id, name="changed")
    with pytest.raises(ConflictError):
        assets.delete("p", asset.id)
    with factory() as uow:
        assert uow.assets.get(asset.id).name == asset.name
    assert assets.storage.resolve("p", asset.project_relative_path).read_bytes() == b"original"


def test_archived_task_results_can_be_read_but_primary_cannot_change(lifecycle):
    service, factory = lifecycle
    service.transition_tasks("p", ["t0"], "archive")
    results = ResultService(factory)
    assert results.list("p", "t0") == []
    with pytest.raises(ConflictError):
        results.select_primary("p", "t0", "result")


@pytest.mark.parametrize("kind", ["video", "prompt"])
@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING])
@pytest.mark.parametrize("action", ["archive", "trash"])
def test_active_jobs_prevent_batch_and_project_transition(lifecycle, kind, status, action):
    service, factory = lifecycle
    with factory() as uow:
        if kind == "video":
            uow.jobs.add(Job(
                id="busy", project_id="p", task_id="t1", status=status,
                final_prompt_snapshot="frozen", task_content_snapshot={}, assets_snapshot=[],
                generation_profile_snapshot={}, provider_profile_snapshot={},
                params_snapshot={}, context_snapshot={},
            ))
        else:
            uow.prompt_batches.add(PromptEnhancementBatch(
                id="batch", project_id="p", status="running", total_count=1,
            ))
            uow.prompt_jobs.add(PromptEnhancementJob(
                id="busy", batch_id="batch", project_id="p", task_id="t1", status=status,
                source_snapshot={}, context_snapshot={}, provider_profile_snapshot={},
                target_skill="test",
            ))
    with pytest.raises(ConflictError) as error:
        service.transition_tasks("p", ["t0", "t1"], action)
    assert error.value.code == "TASK_BUSY"
    with pytest.raises(ConflictError):
        service.transition_project("p", action)
    with factory() as uow:
        for item in [uow.projects.get("p"), *uow.tasks.list_by_project("p")]:
            assert item.archived_at is None
            assert item.deleted_at is None


def test_active_reordering_preserves_hidden_task_slot(lifecycle):
    service, factory = lifecycle
    with factory() as uow:
        uow.tasks.add(Task(id="t2", project_id="p", display_order=2, title="Third"))
    service.transition_tasks("p", ["t1"], "archive")
    TaskService(factory).reorder("p", ["t2", "t0"])
    with factory() as uow:
        assert [task.id for task in uow.tasks.list_by_project("p")] == ["t2", "t1", "t0"]
        assert uow.tasks.get("t1").archived_at is not None
    service.transition_tasks("p", ["t1"], "unarchive")
    with factory() as uow:
        assert [task.id for task in uow.tasks.list_by_project("p")] == ["t2", "t1", "t0"]


def test_prompt_eligibility_skips_archived_tasks(lifecycle):
    service, factory = lifecycle
    with factory() as uow:
        for task in uow.tasks.list_by_project("p"):
            task.user_prompt = "A scene"
            uow.tasks.update(task)
    service.transition_tasks("p", ["t0"], "archive")
    batch = BatchProductionService(factory, None, None)
    result = batch.prompt_batch_eligibility("p", ["t0", "t1"])
    assert result.eligible_task_ids == ["t1"]
    assert [(item.task_id, item.reason) for item in result.skipped] == [("t0", "read-only")]
