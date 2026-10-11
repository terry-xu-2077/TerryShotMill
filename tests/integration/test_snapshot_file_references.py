from copy import deepcopy

import pytest
from shotmill.application.snapshot_files import freeze_media_references
from shotmill.domain.entities import TaskAssetBinding
from shotmill.errors import ConflictError
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_missing_shared_reference_does_not_reject_other_prompt_batch_tasks(client):
    container = client.app.state.container
    service = container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    project = _project(client)["id"]
    broken = _task(client, project, "Broken", "Enhance")["id"]
    healthy = _task(client, project, "Healthy", "Enhance")["id"]
    valid = container.asset_service.import_bytes(project, "valid.png", b"valid")
    asset = container.asset_service.import_bytes(project, "missing.png", b"image")
    with service.uow_factory() as uow:
        task = uow.tasks.get(broken)
        task.asset_bindings = [
            TaskAssetBinding(valid.id, "<Picture 1>"),
            TaskAssetBinding(asset.id, "<Picture 2>"),
        ]
        uow.tasks.update(task)
        uow.files.release_owner("project", project, "asset", asset.id)
    response = client.post(f"/api/v1/projects/{project}/prompt-enhancement-batches", json={
        "taskIds": [broken, healthy],
    })
    assert response.status_code == 202, response.text
    for job_id in queue.jobs:
        client.portal.call(service._execute_prompt_job, job_id)
    with service.uow_factory() as uow:
        jobs = uow.prompt_jobs.list_by_batch(response.json()["batchId"])
        states = {job.task_id: job.status.value for job in jobs}
        assert states == {broken: "failed", healthy: "completed"}
        failed = next(job for job in jobs if job.task_id == broken)
        assert uow.files.get_reference(
            "project", project, "prompt_job", failed.id, "input-0",
        ) is None
    queued_before = list(queue.jobs)
    retried = client.post(
        f"/api/v1/projects/{project}/prompt-enhancement-batches/{failed.batch_id}/retry-failed",
    )
    assert retried.status_code == 202, retried.text
    assert queue.jobs == queued_before
    with service.uow_factory() as uow:
        batch = uow.prompt_batches.get(retried.json()["batchId"])
        assert batch.queued_count == 0
        assert batch.failed_count == 1
    assert container.storage.resolve(project, valid.project_relative_path).read_bytes() == b"valid"


def test_submitted_video_job_keeps_own_input_reference(client):
    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    project = _project(client)["id"]
    task_id = _task(client, project, "Snapshot", "Generate")["id"]
    asset = container.asset_service.import_bytes(
        project, "input.png", b"image", content_type="image/png",
    )
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.asset_bindings = [TaskAssetBinding(asset.id, "<Picture 1>")]
        uow.tasks.update(task)
    response = client.post(f"/api/v1/projects/{project}/tasks/{task_id}/generation", json={})
    assert response.status_code == 202, response.text
    job = service.get_job(response.json()["id"])
    path = job.assets_snapshot[0]["projectRelativePath"]
    assert path == f"shared/job/{job.id}/input-0"
    assert path != asset.project_relative_path
    with service.uow_factory() as uow:
        # Simulate releasing the mutable asset owner, without changing the job.
        uow.files.release_owner("project", project, "asset", asset.id)
    assert container.storage.resolve(project, path).read_bytes() == b"image"
    assert service._provider_request(job).assets[0].original_filename == "input.png"


def test_freezing_is_copy_on_write_and_cannot_borrow_another_project_reference(client):
    container = client.app.state.container
    factory = container.generation_service.uow_factory
    project = _project(client)["id"]
    other = _project(client)["id"]
    asset = container.asset_service.import_bytes(project, "file.png", b"image")
    media = [{"assetId": asset.id, "projectRelativePath": asset.project_relative_path}]
    original = deepcopy(media)
    with factory() as uow:
        frozen = freeze_media_references(uow, project, "job", "j", media)
        assert frozen[0]["projectRelativePath"] == "shared/job/j/input-0"
        assert media == original
    with pytest.raises(ConflictError), factory() as uow:
        freeze_media_references(uow, other, "job", "foreign", media)
    with factory() as uow:
        assert uow.files.get_reference("project", other, "job", "foreign", "input-0") is None


@pytest.mark.parametrize("retry", [False, True])
def test_prompt_job_executes_with_frozen_media_after_asset_reference_release(
    client, providers, monkeypatch, retry,
):
    container = client.app.state.container
    service = container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    project = _project(client)["id"]
    task_id = _task(client, project, "Snapshot", "Enhance")["id"]
    asset = container.asset_service.import_bytes(project, "input.png", b"image")
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.asset_bindings = [TaskAssetBinding(asset.id, "<Picture 1>")]
        uow.tasks.update(task)
    response = client.post(f"/api/v1/projects/{project}/prompt-enhancement-batches", json={
        "taskIds": [task_id],
    })
    assert response.status_code == 202, response.text
    with service.uow_factory() as uow:
        job = uow.prompt_jobs.get(queue.jobs[0])
        media = job.source_snapshot["media"][0]
        assert media["projectRelativePath"] == f"shared/prompt_job/{job.id}/input-0"
        uow.files.release_owner("project", project, "asset", asset.id)
    if retry:
        async def fail(request):
            raise RuntimeError("Injected provider failure")

        with monkeypatch.context() as patch:
            patch.setattr(providers[0], "enhance", fail)
            result = client.portal.call(service._execute_prompt_job, job.id)
            assert result.state == "failed"
        response = client.post(
            f"/api/v1/projects/{project}/prompt-enhancement-batches/{job.batch_id}/retry-failed",
        )
        assert response.status_code == 202, response.text
        with service.uow_factory() as uow:
            original = uow.prompt_jobs.get(job.id)
            job = uow.prompt_jobs.get(queue.jobs[-1])
            assert original.source_snapshot["media"][0] == media
            assert job.source_snapshot["media"][0]["projectRelativePath"] == (
                f"shared/prompt_job/{job.id}/input-0"
            )
            uow.files.release_owner("project", project, "prompt_job", original.id)
    result = client.portal.call(service._execute_prompt_job, job.id)
    assert result.state == "completed"
    actual = providers[0].requests[-1].media[0]
    assert actual.path.read_bytes() == b"image"
    assert actual.original_filename == "input.png"


def test_task_purge_releases_prompt_history_but_keeps_project_asset(client):
    container = client.app.state.container
    service = container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    project = _project(client)["id"]
    task_id = _task(client, project, "History", "Enhance")["id"]
    asset = container.asset_service.import_bytes(project, "input.png", b"image")
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.asset_bindings = [TaskAssetBinding(asset.id, "<Picture 1>")]
        uow.tasks.update(task)
    response = client.post(f"/api/v1/projects/{project}/prompt-enhancement-batches", json={
        "taskIds": [task_id],
    })
    assert response.status_code == 202, response.text
    job_id = queue.jobs[0]
    assert client.portal.call(service._execute_prompt_job, job_id).state == "completed"
    with service.uow_factory() as uow:
        assert uow.files.get_reference("project", project, "prompt_job", job_id, "input-0")
    container.removal_service.delete_tasks(project, [task_id])
    with service.uow_factory() as uow:
        assert uow.prompt_jobs.get(job_id) is None
        assert uow.files.get_reference(
            "project", project, "prompt_job", job_id, "input-0",
        ) is None
        assert uow.files.get_reference("project", project, "asset", asset.id, "content")
    assert client.get(f"/media/{project}/{asset.project_relative_path}").content == b"image"
