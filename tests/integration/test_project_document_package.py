from dataclasses import replace
from io import BytesIO

from shotmill.application.container import build_container
from shotmill.media.project_package import open_project_package
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_zip_opens_without_source_project_database_or_external_media(client, tmp_path):
    source = client.app.state.container
    project_id = _project(client)["id"]
    task_id = _task(client, project_id, "Timeline", "Prompt")["id"]
    arranged = client.patch(f"/api/v1/projects/{project_id}/tasks/{task_id}/timeline", json={
        "startSeconds": 3.5, "durationSeconds": 7.25,
    })
    assert arranged.status_code == 200, arranged.text
    external = tmp_path / "outside" / "source.png"
    external.parent.mkdir()
    external.write_bytes(b"original picture")
    asset = source.asset_service.import_path(project_id, external)
    source.generation_service.attach_queue(HeldQueue())
    submitted = client.post(f"/api/v1/projects/{project_id}/tasks/{task_id}/generation", json={})
    assert submitted.status_code == 202, submitted.text
    client.portal.call(source.generation_service.execute, submitted.json()["id"])
    with source.project_export_service.prepare(project_id) as archive:
        package_bytes = archive.read_bytes()
    with open_project_package(BytesIO(package_bytes)) as package:
        assert package.document["projectId"] == project_id
        assert package.document["tables"]["generation_tasks"][0]["id"] == task_id
        assert package.document["tables"]["generation_tasks"][0]["timeline_start_seconds"] == 3.5
        assert package.files[f"project.files/{asset.project_relative_path}"].read_bytes() == b"original picture"
        result = package.document["tables"]["results"][0]
        result_path = result["video_url"].removeprefix(f"/media/{project_id}/")
        assert package.files[f"project.files/{result_path}"].read_bytes()

    hidden = external.with_suffix(".hidden")
    external.rename(hidden)
    original_media = source.project_documents.media_root(project_id)
    hidden_media = original_media.with_name(original_media.name + ".hidden")
    original_media.rename(hidden_media)
    try:
        destination = tmp_path / "unpacked" / "Imported.shotmill"
        destination.parent.mkdir()
        imported = build_container(replace(source.settings, data_root=tmp_path / "other-app"))
        try:
            outcome = imported.project_import_service.import_package(BytesIO(package_bytes), destination)
            assert outcome.project_id == project_id
            assert destination.is_file()
            assert imported.project_file_reader.read(project_id, asset.project_relative_path).path.read_bytes() == b"original picture"
            assert imported.project_file_reader.read(project_id, result_path).path.read_bytes()
            assert imported.workspace_query.workspace(project_id).tasks[0].id == task_id
            assert imported.workspace_query.workspace(project_id).tasks[0].timeline_start_seconds == 3.5
            assert imported.imported_generation_configuration.pending(project_id)[0].task_id == task_id
        finally:
            imported.engine.dispose()
        reopened = build_container(replace(source.settings, data_root=tmp_path / "third-app"))
        try:
            assert reopened.project_documents.open(destination) == project_id
            assert reopened.project_file_reader.read(project_id, asset.project_relative_path).path.read_bytes() == b"original picture"
            assert reopened.project_file_reader.read(project_id, result_path).path.read_bytes()
        finally:
            reopened.engine.dispose()
    finally:
        hidden.rename(external)
        hidden_media.rename(original_media)
