from copy import deepcopy

from shotmill.application.project_transfer_identity import remap_project_identity
from shotmill.domain.entities import (
    AiPromptRevision,
    Asset,
    ContextLink,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    TaskAssetBinding,
    utcnow,
)
from shotmill.domain.enums import JobStatus
from test_project_transfer_validation import graph


def test_import_allocates_independent_ids_without_replacing_prompt_text():
    source = graph()
    source.tasks[0].primary_result_id = "r"
    source.tasks[0].user_prompt = "Keep literal task t, result r, project p unchanged"
    source.assets = [Asset("a", "p", "a", "a.png", "assets/a.png", "image")]
    source.tasks[0].asset_bindings = [TaskAssetBinding("a", "<Picture 1>")]
    source.tasks[0].generation_params = {"workflowInputs": {"slots": [{"assetId": "a"}]}}
    source.jobs[0].assets_snapshot = [{"assetId": "a", "projectRelativePath": "assets/a.png"}]
    original = deepcopy(source)
    first, second = remap_project_identity(source), remap_project_identity(source)
    assert source == original
    assert first.source.project.id != second.source.project.id != "p"
    task = first.source.tasks[0]
    assert task.id != "t"
    assert task.user_prompt == source.tasks[0].user_prompt
    assert task.primary_result_id == first.source.results[0].id
    assert first.source.results[0].job_id == first.source.jobs[0].id
    assert first.source.jobs[0].task_id == task.id
    assert task.asset_bindings[0].asset_id == first.source.assets[0].id
    assert first.source.jobs[0].assets_snapshot[0]["assetId"] == first.source.assets[0].id
    assert task.generation_params["workflowInputs"]["slots"][0]["assetId"] == (
        first.source.assets[0].id
    )
    assert first.source.placements[0].task_id == task.id
    assert first.source.placements[0].scene_id == first.source.scenes[0].id


def test_missing_context_identity_is_new_but_stays_missing():
    source = graph()
    source.contexts = [ContextLink(
        "c", "p", "deleted-task", "t", "last-frame", source_result_id="deleted-result",
        source_deleted_at=utcnow(), source_task_title="Deleted task",
    )]
    remapped = remap_project_identity(source)
    link = remapped.source.contexts[0]
    assert link.source_task_id != "deleted-task"
    assert link.source_task_id not in {task.id for task in remapped.source.tasks}
    assert link.source_result_id != "deleted-result"
    assert link.source_deleted_at == source.contexts[0].source_deleted_at
    assert link.source_task_title == "Deleted task"


def test_prompt_history_and_review_use_same_new_revision_identity():
    source = graph()
    source.prompt_batches = [PromptEnhancementBatch("b", "p", "completed", 1)]
    source.prompt_revisions = [AiPromptRevision(
        "revision", "p", "t", "Original", "Enhanced", [], False, False, "skill", "1",
    )]
    source.prompt_jobs = [PromptEnhancementJob(
        "pj", "b", "p", "t", JobStatus.COMPLETED, {"userPrompt": "Original"}, {}, {},
        "skill", revision_id="revision",
    )]
    source.tasks[0].approved_revision_id = "revision"
    source.tasks[0].user_prompt_history = [{"id": "u", "prompt": "literal u", "createdAt": "old"}]
    source.tasks[0].generation_params = {"workflowInputs": {"slots": [{"assetId": ""}]}}
    result = remap_project_identity(source).source
    assert result.tasks[0].approved_revision_id == result.prompt_revisions[0].id
    assert result.prompt_jobs[0].revision_id == result.prompt_revisions[0].id
    assert result.prompt_jobs[0].batch_id == result.prompt_batches[0].id
    assert result.prompt_jobs[0].task_id == result.tasks[0].id
    assert result.tasks[0].user_prompt_history[0]["id"] != "u"
    assert result.tasks[0].user_prompt_history[0]["prompt"] == "literal u"
    assert result.tasks[0].generation_params["workflowInputs"]["slots"][0]["assetId"] == ""
