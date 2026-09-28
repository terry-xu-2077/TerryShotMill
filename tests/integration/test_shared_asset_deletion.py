from dataclasses import replace

import pytest
from shotmill.domain.entities import TaskAssetBinding, utcnow
from shotmill.persistence.repositories.files import SqlAlchemyFileRepository
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_asset_deletion_releases_its_owner_but_preserves_other_project_and_job(client):
    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    project, other = _project(client)["id"], _project(client)["id"]
    asset = container.asset_service.import_bytes(project, "input.png", b"shared-image")
    retained = container.asset_service.import_bytes(other, "input.png", b"shared-image")
    task_id = _task(client, project, "History", "Generate")["id"]
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.asset_bindings = [TaskAssetBinding(asset.id, "<Picture 1>")]
        uow.tasks.update(task)
    submitted = client.post(f"/api/v1/projects/{project}/tasks/{task_id}/generation", json={})
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["id"]
    client.portal.call(service.execute, job_id)
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.asset_bindings = []
        uow.tasks.update(task)
        path = uow.jobs.get(job_id).assets_snapshot[0]["projectRelativePath"]
    deleted = client.delete(f"/api/v1/projects/{project}/assets/{asset.id}")
    assert deleted.status_code == 204, deleted.text
    with service.uow_factory() as uow:
        assert uow.files.get_reference("project", project, "asset", asset.id, "content") is None
        assert uow.files.get_reference("project", project, "job", job_id, "input-0")
        assert uow.files.get_reference("project", other, "asset", retained.id, "content")
    assert client.get(f"/media/{project}/{asset.project_relative_path}").status_code == 404
    assert client.get(f"/media/{project}/{path}").content == b"shared-image"
    assert client.get(f"/media/{other}/{retained.project_relative_path}").content == b"shared-image"


def test_asset_reference_release_failure_rolls_back_asset_and_reference(client, monkeypatch):
    container = client.app.state.container
    project = _project(client)["id"]
    asset = container.asset_service.import_bytes(project, "image.png", b"keep")
    original = SqlAlchemyFileRepository.release_owner

    def fail_after_release(self, *args):
        original(self, *args)
        raise RuntimeError("injected reference failure")

    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyFileRepository, "release_owner", fail_after_release)
        with pytest.raises(RuntimeError, match="injected"):
            container.asset_service.delete(project, asset.id)
    with container.generation_service.uow_factory() as uow:
        assert uow.assets.get(asset.id) is not None
        assert uow.files.get_reference("project", project, "asset", asset.id, "content")
    assert client.get(f"/media/{project}/{asset.project_relative_path}").content == b"keep"


@pytest.mark.parametrize("field", ["assets_snapshot", "context_snapshot", "execution_context"])
def test_legacy_job_alias_remains_readable_after_asset_deletion(client, field):
    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    project = _project(client)["id"]
    asset = container.asset_service.import_bytes(project, "legacy.png", b"legacy")
    task_id = _task(client, project, "Legacy history", "Generate")["id"]
    response = client.post(f"/api/v1/projects/{project}/tasks/{task_id}/generation", json={})
    client.portal.call(service.execute, response.json()["id"])
    with service.uow_factory() as uow:
        job = uow.jobs.get(response.json()["id"])
        # Emulate a persisted snapshot from before per-job reference pinning.
        media = [{
            "assetId": asset.id, "projectRelativePath": asset.project_relative_path,
            "originalFilename": asset.original_filename,
        }]
        snapshot = media if field == "assets_snapshot" else {"media": media}
        uow.jobs.add(replace(job, id="legacy-job", **{field: snapshot}))
        task = uow.tasks.get(task_id)
        task.archived_at = utcnow()
        uow.tasks.update(task)
    container.asset_service.delete(project, asset.id)
    assert container.storage.resolve(project, asset.project_relative_path).read_bytes() == b"legacy"
    exported = client.get(f"/api/v1/projects/{project}/export")
    assert exported.status_code == 200, exported.text


def test_legacy_prompt_job_alias_survives_asset_deletion_and_export(client):
    container = client.app.state.container
    service = container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    project = _project(client)["id"]
    task_id = _task(client, project, "Legacy prompt", "Enhance")["id"]
    asset = container.asset_service.import_bytes(project, "legacy.png", b"legacy")
    response = client.post(f"/api/v1/projects/{project}/prompt-enhancement-batches", json={
        "taskIds": [task_id],
    })
    assert response.status_code == 202, response.text
    assert client.portal.call(service._execute_prompt_job, queue.jobs[0]).state == "completed"
    with service.uow_factory() as uow:
        job = uow.prompt_jobs.get(queue.jobs[0])
        uow.prompt_jobs.add(replace(job, id="legacy-prompt", revision_id=None, source_snapshot={
            **job.source_snapshot, "media": [{
                "assetId": asset.id, "projectRelativePath": asset.project_relative_path,
                "originalFilename": asset.original_filename,
            }],
        }))
    container.asset_service.delete(project, asset.id)
    assert container.storage.resolve(project, asset.project_relative_path).read_bytes() == b"legacy"
    exported = client.get(f"/api/v1/projects/{project}/export")
    assert exported.status_code == 200, exported.text
