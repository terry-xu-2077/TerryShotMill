from io import BytesIO

import pytest

from test_batch_review_api import _project, _task


def test_import_rejects_open_source_without_touching_selected_destination(client, tmp_path):
    container = client.app.state.container
    project_id = _project(client)["id"]
    _task(client, project_id, "Original", "Prompt")
    destination = tmp_path / "copy.shotmill"
    with container.project_export_service.prepare(project_id) as archive:
        response = client.post("/api/v1/projects/import", data={"path": str(destination)},
                               files={"file": ("project.zip", archive.read_bytes(), "application/zip")})
    assert response.status_code == 409, response.text
    assert not destination.exists()
    assert not destination.with_name("copy.files").exists()
    assert container.project_documents.paths[project_id].is_file()


def test_import_rejects_existing_files_without_overwriting(client, tmp_path):
    container = client.app.state.container
    project_id = _project(client)["id"]
    destination = tmp_path / "existing.shotmill"
    destination.write_bytes(b"keep this file")
    with container.project_export_service.prepare(project_id) as archive:
        with pytest.raises(FileExistsError):
            container.project_import_service.import_package(
                BytesIO(archive.read_bytes()), destination,
            )
    assert destination.read_bytes() == b"keep this file"
