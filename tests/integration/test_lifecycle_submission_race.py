import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from types import SimpleNamespace

import pytest
from shotmill.application.batch_service import BatchProductionService
from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationService
from shotmill.errors import ConflictError
from shotmill.media.storage import MediaStorage
from shotmill.persistence.repositories.history import (
    SqlAlchemyJobRepository,
    SqlAlchemyPromptEnhancementJobRepository,
)
from test_lifecycle_service import lifecycle  # noqa: F401
from test_prompt_batch_recovery import HeldQueue


@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("target", ["project", "task"])
@pytest.mark.parametrize("kind", ["video", "prompt"])
def test_lifecycle_transition_cannot_race_submission(
    lifecycle, providers, tmp_path, monkeypatch, action, target, kind  # noqa: F811
):
    service, factory = lifecycle
    with factory() as uow:
        task = uow.tasks.get("t0")
        task.user_prompt = "A scene"
        task.final_prompt = "A scene"
        uow.tasks.update(task)
    generation = GenerationService(
        factory, providers[1], MediaStorage(tmp_path / "media"), ProjectEventBus()
    )
    generation.attach_queue(HeldQueue())
    batch = BatchProductionService(
        factory, SimpleNamespace(capture_provider_profile=lambda: {}), generation
    )
    batch.attach_queue(HeldQueue())

    async def submit():
        if kind == "video":
            return await generation.submit("p", "t0")
        return await batch.create_prompt_batch(
            "p", task_ids=["t0"], include_project_background=False,
            include_previous_task_summary=False,
        )
    idle_checked, release = Event(), Event()
    original = service._ensure_idle

    def hold_after_idle_check(*args):
        original(*args)
        idle_checked.set()
        assert release.wait(5), "test failed to release lifecycle transaction"

    monkeypatch.setattr(service, "_ensure_idle", hold_after_idle_check)

    def transition():
        if target == "project":
            return service.transition_project("p", action)
        return service.transition_tasks("p", ["t0"], action)

    with ThreadPoolExecutor(max_workers=2) as workers:
        changing = workers.submit(transition)
        assert idle_checked.wait(5)
        submitting = workers.submit(lambda: asyncio.run(submit()))
        try:
            # Old code can commit a new job after the deletion's idle check.
            # Serialized code waits; release the first transaction in either case.
            try:
                submitting.result(timeout=0.3)
            except (TimeoutError, ConflictError):
                pass
        finally:
            release.set()
        changing.result(timeout=5)
        if kind == "prompt" and target == "task":
            items = submitting.result(timeout=5).items
            assert len(items) == 1
            assert items[0].state == "skipped"
        else:
            with pytest.raises(ConflictError) as error:
                submitting.result(timeout=5)
            assert error.value.code == "OBJECT_READ_ONLY"
    with factory() as uow:
        assert uow.jobs.list_by_task("t0") == []
        assert uow.prompt_jobs.active_task_ids_by_project("p") == set()
        item = uow.projects.get("p") if target == "project" else uow.tasks.get("t0")
        assert getattr(item, "archived_at" if action == "archive" else "deleted_at") is not None


@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("target", ["project", "task"])
@pytest.mark.parametrize("kind", ["video", "prompt"])
def test_submission_winning_transaction_prevents_lifecycle_change(
    lifecycle, providers, tmp_path, monkeypatch, action, target, kind  # noqa: F811
):
    service, factory = lifecycle
    with factory() as uow:
        task = uow.tasks.get("t0")
        task.user_prompt = task.final_prompt = "A scene"
        uow.tasks.update(task)
    generation = GenerationService(
        factory, providers[1], MediaStorage(tmp_path / "media"), ProjectEventBus()
    )
    generation.attach_queue(HeldQueue())
    batch = BatchProductionService(
        factory, SimpleNamespace(capture_provider_profile=lambda: {}), generation
    )
    batch.attach_queue(HeldQueue())
    inserting, release = Event(), Event()
    repository = (
        SqlAlchemyJobRepository if kind == "video" else SqlAlchemyPromptEnhancementJobRepository
    )
    original = repository.add

    def held_add(repo, job):
        original(repo, job)
        inserting.set()
        assert release.wait(5)

    monkeypatch.setattr(repository, "add", held_add)

    async def submit():
        if kind == "video":
            return await generation.submit("p", "t0")
        return await batch.create_prompt_batch(
            "p", task_ids=["t0"], include_project_background=False,
            include_previous_task_summary=False,
        )

    def transition():
        if target == "project":
            return service.transition_project("p", action)
        return service.transition_tasks("p", ["t0"], action)

    with ThreadPoolExecutor(max_workers=2) as workers:
        submitting = workers.submit(lambda: asyncio.run(submit()))
        assert inserting.wait(5)
        changing = workers.submit(transition)
        try:
            try:
                changing.result(timeout=0.3)
            except (TimeoutError, ConflictError):
                pass
        finally:
            release.set()
        submitting.result(timeout=5)
        with pytest.raises(ConflictError) as error:
            changing.result(timeout=5)
        assert error.value.code == "TASK_BUSY"
    with factory() as uow:
        active = (uow.jobs if kind == "video" else uow.prompt_jobs).active_task_ids_by_project("p")
        assert active == {"t0"}
        for item in (uow.projects.get("p"), uow.tasks.get("t0")):
            assert item.archived_at is None and item.deleted_at is None
