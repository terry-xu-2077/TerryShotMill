import pytest
from shotmill.application.project_export_service import ProjectExportService
from shotmill.media.project_package import PackageLimits, open_project_package
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def exporter(container):
    return ProjectExportService(
        container.generation_service.uow_factory, container.file_library,
        container.project_documents, container.storage,
    )


def test_export_service_produces_complete_private_zip_and_cleans_after_download(client):
    container = client.app.state.container
    project = _project(client)["id"]
    task = _task(client, project, "Export me", "Original prompt")["id"]
    asset = container.asset_service.import_bytes(project, "image.png", b"image")
    with exporter(container).prepare(project) as path:
        assert path.is_file()
        with path.open("rb") as stream, open_project_package(stream) as package:
            assert package.document["version"] == 2
            assert package.document["projectId"] == project
            assert package.document["tables"]["generation_tasks"][0]["id"] == task
            assert package.document["tables"]["generation_tasks"][0]["user_prompt"] == "Original prompt"
            assert package.files[f"project.files/{asset.project_relative_path}"].read_bytes() == b"image"
        with container.generation_service.uow_factory() as uow:
            uow.reserve_write()  # Export no longer holds the database during download.
            assert uow.projects.get(project) is not None
    assert not path.exists()
    assert container.storage.resolve(project, asset.project_relative_path).read_bytes() == b"image"


def test_export_failure_exposes_no_partial_zip_and_retry_succeeds(client):
    container = client.app.state.container
    project = _project(client)["id"]
    container.asset_service.import_bytes(project, "image.png", b"image")
    service = exporter(container)
    staging = container.file_library.storage.managed.resolve("staging")
    before = set(staging.iterdir())
    with pytest.raises(ValueError, match="size limit"), service.prepare(
        project, limits=PackageLimits(max_file_bytes=1),
    ):
        pytest.fail("Incomplete export became visible")
    assert set(staging.iterdir()) == before
    with service.prepare(project) as path:
        assert path.stat().st_size > 0
    assert set(staging.iterdir()) == before


def test_interrupted_download_cleans_only_owned_export(client):
    container = client.app.state.container
    project = _project(client)["id"]
    with pytest.raises(RuntimeError), exporter(container).prepare(project) as path:
        raise RuntimeError("Client disconnected")
    assert not path.exists()
    assert client.get(f"/api/v1/projects/{project}/workspace").status_code == 200


def test_export_actual_completed_generation_history(client):
    container = client.app.state.container
    project = _project(client)["id"]
    task = _task(client, project, "Generate", "Video prompt")["id"]
    generation = container.generation_service
    generation.attach_queue(HeldQueue())
    submitted = client.post(f"/api/v1/projects/{project}/tasks/{task}/generation", json={})
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["id"]
    client.portal.call(generation.execute, job_id)
    with exporter(container).prepare(project) as path:
        with path.open("rb") as stream, open_project_package(stream) as package:
            assert package.document["tables"]["jobs"][0]["id"] == job_id
            assert package.document["tables"]["jobs"][0]["status"] == "completed"
            assert package.document["tables"]["results"]
            for result in package.document["tables"]["results"]:
                relative = result["video_url"].removeprefix(f"/media/{project}/")
                assert package.files[f"project.files/{relative}"].read_bytes()
