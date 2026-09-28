import pytest
from shotmill.application.project_import_service import ProjectImportService
from shotmill.persistence.repositories.task import SqlAlchemyTaskRepository
from test_batch_review_api import _project, _task
from test_project_export_service import exporter
from test_prompt_batch_recovery import HeldQueue


def test_project_zip_import_retains_history_with_new_ids_and_shared_bytes(client):
    container = client.app.state.container
    generation = container.generation_service
    generation.attach_queue(HeldQueue())
    project = _project(client)["id"]
    task = _task(client, project, "Original", "Prompt")["id"]
    asset = container.asset_service.import_bytes(project, "input.png", b"image")
    response = client.post(f"/api/v1/projects/{project}/tasks/{task}/generation", json={})
    assert response.status_code == 202
    client.portal.call(generation.execute, response.json()["id"])
    importer = ProjectImportService(generation.uow_factory, container.file_library)
    with exporter(container).prepare(project) as path:
        with path.open("rb") as stream:
            outcome = importer.import_package(stream)
        with path.open("rb") as stream:
            another = importer.import_package(stream)
    assert len({project, outcome.project_id, another.project_id}) == 3
    with generation.uow_factory() as uow:
        tasks = uow.tasks.list_by_project(outcome.project_id)
        assert len(tasks) == 1 and tasks[0].id != task
        assert tasks[0].user_prompt == "Prompt"
        results = uow.results.list_by_task(tasks[0].id)
        assert results and tasks[0].primary_result_id == results[0].id
        assert uow.jobs.get(results[0].job_id).task_id == tasks[0].id
        imported_asset = uow.assets.list_by_project(outcome.project_id)[0]
    assert container.storage.resolve(outcome.project_id, imported_asset.project_relative_path) == (
        container.storage.resolve(project, asset.project_relative_path)
    )
    assert client.get(results[0].video_url).status_code == 200
    assert client.get(f"/api/v1/projects/{outcome.project_id}/workspace").status_code == 200


def test_import_save_failure_rolls_back_project_and_new_references(client, monkeypatch):
    container = client.app.state.container
    project = _project(client)["id"]
    _task(client, project, "Original", "Prompt")
    asset = container.asset_service.import_bytes(project, "input.png", b"image")
    factory = container.generation_service.uow_factory
    with factory() as uow:
        previous = {item.id for item in uow.projects.list()}
        refs = uow.files.references(asset.hash)

    def fail(*args):
        raise RuntimeError("Injected task save failure")

    with exporter(container).prepare(project) as path:
        monkeypatch.setattr(SqlAlchemyTaskRepository, "add", fail)
        with path.open("rb") as stream, pytest.raises(RuntimeError):
            ProjectImportService(factory, container.file_library).import_package(stream)
    with factory() as uow:
        assert {item.id for item in uow.projects.list()} == previous
        assert uow.files.references(asset.hash) == refs
    assert container.storage.resolve(project, asset.project_relative_path).read_bytes() == b"image"
