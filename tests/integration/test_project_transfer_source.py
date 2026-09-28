import pytest
from shotmill.application.project_transfer_source import read_project_transfer_source
from shotmill.domain.entities import (
    AiPromptRevision,
    ContextLink,
    Job,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Result,
    Scene,
    TaskPlacement,
    utcnow,
)
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError, NotFoundError
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_source_includes_hidden_tasks_all_results_and_structure(client):
    project = _project(client)["id"]
    other = _project(client)["id"]
    task_id = _task(client, project, "Trash", "Prompt")["id"]
    archived = _task(client, project, "Archive", "Prompt")["id"]
    _task(client, other, "Foreign", "Prompt")
    factory = client.app.state.container.generation_service.uow_factory
    with factory() as uow:
        task = uow.tasks.get(task_id)
        task.deleted_at = utcnow()
        uow.tasks.update(task)
        task = uow.tasks.get(archived)
        task.archived_at = utcnow()
        uow.tasks.update(task)
        uow.story_structure.add_scene(Scene(
            "hidden", project, number=2, title="Hidden scene", order_key=2,
        ))
        uow.story_structure.place_task(project, TaskPlacement(task_id, "hidden", 42))
        uow.jobs.add(Job(
            "job", project, task_id, JobStatus.COMPLETED, "Prompt", {}, [], {}, {}, {}, {},
        ))
        for index in range(2):
            uow.results.add(Result(
                f"result-{index}", project, task_id, "job", f"/media/{project}/{index}.mp4",
            ))
        uow.prompt_batches.add(PromptEnhancementBatch(
            "history-batch", project, "completed", 1, completed_count=1,
        ))
        uow.prompt_revisions.add(AiPromptRevision(
            "revision", project, task_id, "Original", "Enhanced", [],
            False, False, "minimax-h3", "1",
        ))
        uow.prompt_jobs.add(PromptEnhancementJob(
            "history-prompt", "history-batch", project, task_id, JobStatus.COMPLETED,
            {"userPrompt": "Original"}, {}, {}, "minimax-h3", revision_id="revision",
        ))
        uow.contexts.replace_for_target(archived, [ContextLink(
            "missing", project, "deleted-source", archived, "last-frame",
            source_deleted_at=utcnow(), source_task_title="Deleted source",
        )])
    with factory() as uow:
        source = read_project_transfer_source(uow, project)
        assert {task.id for task in source.tasks} == {task_id, archived}
        assert len(source.results) == 2
        assert source.jobs[0].id == "job"
        assert source.prompt_revisions[0].output_prompt == "Enhanced"
        assert source.prompt_jobs[0].revision_id == "revision"
        assert source.prompt_batches[0].id == "history-batch"
        assert any(scene.id == "hidden" for scene in source.scenes)
        assert TaskPlacement(task_id, "hidden", 42) in source.placements
        assert source.contexts[0].source_deleted_at is not None
        assert source.contexts[0].source_task_id == "deleted-source"


@pytest.mark.parametrize("kind", ["video", "prompt"])
@pytest.mark.parametrize("state", [JobStatus.QUEUED, JobStatus.RUNNING])
def test_source_rejects_either_active_queue(client, kind, state):
    project = _project(client)["id"]
    task = _task(client, project, "Active", "Prompt")["id"]
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    with service.uow_factory() as uow:
        if kind == "video":
            uow.jobs.add(Job("job", project, task, state, "Prompt", {}, [], {}, {}, {}, {}))
        else:
            uow.prompt_batches.add(PromptEnhancementBatch("batch", project, "queued", 1))
            uow.prompt_jobs.add(PromptEnhancementJob(
                "promptjob", "batch", project, task, state, {}, {}, {}, "minimax-h3",
            ))
    with pytest.raises(ConflictError) as error, service.uow_factory() as uow:
        read_project_transfer_source(uow, project)
    assert error.value.code == "PROJECT_TRANSFER_BUSY"


def test_source_missing_project(client):
    factory = client.app.state.container.generation_service.uow_factory
    with pytest.raises(NotFoundError), factory() as uow:
        read_project_transfer_source(uow, "missing")
