from io import BytesIO
from zipfile import ZipFile

import anyio
import pytest
from shotmill.api.project_transfer import _ExportResponse
from test_batch_review_api import _project


def test_prepared_download_streams_once_and_cleans_package(client):
    project = _project(client)["id"]
    response = client.post(f"/api/v1/projects/{project}/exports")
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["token"]
    assert response.json()["expiresInSeconds"] == 300
    staging = client.app.state.container.file_library.storage.managed.resolve("staging")
    assert len(list(staging.glob("project-export-*"))) == 1
    downloaded = client.get(f"/api/v1/projects/exports/{token}")
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(downloaded.content)) as archive:
        assert "manifest.json" in archive.namelist()
    assert not list(staging.glob("project-export-*"))
    assert client.get(f"/api/v1/projects/exports/{token}").status_code == 404


def test_discard_is_idempotent_and_cannot_download_cancelled_export(client):
    project = _project(client)["id"]
    token = client.post(f"/api/v1/projects/{project}/exports").json()["token"]
    for _ in range(2):
        assert client.delete(f"/api/v1/projects/exports/{token}").status_code == 204
    assert client.get(f"/api/v1/projects/exports/{token}").status_code == 404
    staging = client.app.state.container.file_library.storage.managed.resolve("staging")
    assert not list(staging.glob("project-export-*"))


def test_export_preparation_failure_is_safe_json_and_retryable(client, monkeypatch):
    project = _project(client)["id"]
    service = client.app.state.container.project_export_downloads

    def fail(project_id):
        raise OSError("C:/private/path secret details")

    with monkeypatch.context() as patch:
        patch.setattr(service, "prepare", fail)
        response = client.post(f"/api/v1/projects/{project}/exports")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PROJECT_EXPORT_STORAGE_ERROR"
    assert "private" not in response.text
    assert client.post(f"/api/v1/projects/{project}/exports").status_code == 201


def test_unknown_project_does_not_create_download(client):
    response = client.post("/api/v1/projects/unknown/exports")
    assert response.status_code == 404
    staging = client.app.state.container.file_library.storage.managed.resolve("staging")
    assert not list(staging.glob("project-export-*"))


def test_download_disconnect_cleans_claimed_file_without_touching_project(client):
    project = _project(client)["id"]
    downloads = client.app.state.container.project_export_downloads
    token = downloads.prepare(project)
    path, lifetime = downloads.claim(token)
    response = _ExportResponse(path, lifetime)

    async def send(message):
        raise RuntimeError("client disconnected")

    async def receive():
        return {"type": "http.disconnect"}

    async def stream():
        await response({"type": "http", "method": "GET", "headers": []}, receive, send)

    with pytest.raises(RuntimeError, match="client disconnected"):
        anyio.run(stream)
    assert not path.exists()
    assert client.get(f"/api/v1/projects/{project}/workspace").status_code == 200
