import pytest
from shotmill.application.imported_generation_configuration import ImportedGenerationConfiguration
from shotmill.errors import ConflictError
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_import_requires_configuration_for_single_and_batch_generation(client):
    container = client.app.state.container
    container.generation_service.attach_queue(HeldQueue())
    project = _project(client)["id"]
    _task(client, project, "Imported task", "Prompt")
    exported = client.get(f"/api/v1/projects/{project}/export")
    imported = client.post("/api/v1/projects/import", files={
        "file": ("project.zip", exported.content, "application/zip"),
    })
    assert imported.status_code == 201, imported.text
    destination = imported.json()["projectId"]
    workspace = client.get(f"/api/v1/projects/{destination}/workspace").json()
    task = workspace["tasks"][0]["id"]
    response = client.post(f"/api/v1/projects/{destination}/tasks/{task}/generation", json={})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "GENERATION_CONFIGURATION_REQUIRED"
    preview = client.post(f"/api/v1/projects/{destination}/video-generation-batches/eligibility",
                          json={"taskIds": [task]})
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligibleTaskIds"] == []
    assert preview.json()["skipped"][0]["code"] == "GENERATION_CONFIGURATION_REQUIRED"
    with container.generation_service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task) == []
        assert uow.tasks.generation_configuration_required(task)
        edited = uow.tasks.get(task)
        edited.title = "Renamed without confirming configuration"
        uow.tasks.update(edited)
    with container.generation_service.uow_factory() as uow:
        assert uow.tasks.generation_configuration_required(task)
        original_task = uow.tasks.list_by_project(project)[0]
        assert not uow.tasks.generation_configuration_required(original_task.id)


def test_configuration_confirmation_is_explicit_revision_checked_and_persistent(client):
    container = client.app.state.container
    project = _project(client)["id"]
    task_id = _task(client, project, "Task", "Prompt")["id"]
    factory = container.generation_service.uow_factory
    service = ImportedGenerationConfiguration(factory, lambda: {"local-profile"})
    with factory() as uow:
        task = uow.tasks.get(task_id)
        task.generation_params["workflowProfileId"] = "local-profile"
        uow.tasks.update(task)
        uow.tasks.set_generation_configuration_required(task_id, True)
    pending = service.pending(project)
    assert len(pending) == 1 and pending[0].source_configuration_id == "local-profile"
    for profile, revision in [("unavailable", pending[0].revision),
                              ("local-profile", pending[0].revision + 1)]:
        with pytest.raises(ConflictError):
            service.confirm(project, task_id, profile, revision)
        assert len(service.pending(project)) == 1
    service.confirm(project, task_id, "local-profile", pending[0].revision)
    assert service.pending(project) == []
    with factory() as uow:
        assert not uow.tasks.generation_configuration_required(task_id)
        assert uow.tasks.get(task_id).revision == pending[0].revision + 1
        assert uow.tasks.get(task_id).generation_params["workflowProfileId"] == "local-profile"
    container.generation_service.attach_queue(HeldQueue())
    submitted = client.post(f"/api/v1/projects/{project}/tasks/{task_id}/generation", json={})
    assert submitted.status_code == 202, submitted.text


def test_configuration_api_lists_pending_and_confirms_selection(client, monkeypatch):
    container = client.app.state.container
    project = _project(client)["id"]
    task_id = _task(client, project, "Pending", "Prompt")["id"]
    with container.generation_service.uow_factory() as uow:
        uow.tasks.set_generation_configuration_required(task_id, True)
    monkeypatch.setattr(container.imported_generation_configuration, "available_ids",
                        lambda: {"chosen-profile"})
    url = f"/api/v1/projects/{project}/import-configuration"
    pending = client.get(url)
    assert pending.status_code == 200
    assert pending.json()[0]["taskId"] == task_id
    assert pending.json()[0]["readOnly"] is False
    result = client.post(f"{url}/{task_id}/confirm", json={
        "configurationId": "chosen-profile", "revision": pending.json()[0]["revision"],
    })
    assert result.status_code == 204, result.text
    assert client.get(url).json() == []
