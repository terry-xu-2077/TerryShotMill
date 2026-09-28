import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_http_zip_export_import_and_temporary_cleanup(client):
    container = client.app.state.container
    project = _project(client)["id"]
    _task(client, project, "Portable", "Prompt")
    staging = container.file_library.storage.managed.resolve("staging")
    exported = client.get(f"/api/v1/projects/{project}/export")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/zip"
    assert "attachment" in exported.headers["content-disposition"]
    assert not list(staging.glob("project-export-*"))
    imported = client.post("/api/v1/projects/import", files={
        "file": ("project.zip", exported.content, "application/zip"),
    })
    assert imported.status_code == 201, imported.text
    new_project = imported.json()["projectId"]
    assert new_project != project
    assert client.get(f"/api/v1/projects/{new_project}/workspace").status_code == 200
    assert not list(staging.glob("shotmill-import-*"))


def test_invalid_upload_creates_no_project(client):
    before = client.get("/api/v1/projects").json()
    response = client.post("/api/v1/projects/import", files={"file": ("bad.zip", b"bad")})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROJECT_PACKAGE_INVALID"
    assert client.get("/api/v1/projects").json() == before


def test_imported_provider_requirements_survive_repeated_export(client):
    project = _project(client)["id"]
    exported = client.get(f"/api/v1/projects/{project}/export")
    with ZipFile(BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    requirements = [{"kind": "video", "requiresConfiguration": True,
                     "providerId": "comfyui", "workflowId": "historical-workflow.json"}]
    manifest["records"]["providerRequirements"] = requirements
    package = BytesIO()
    with ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    payload = package.getvalue()
    for _ in range(3):
        imported = client.post("/api/v1/projects/import", files={"file": ("project.zip", payload)})
        assert imported.status_code == 201, imported.text
        assert imported.json()["providerRequirements"] == requirements
        project = imported.json()["projectId"]
        exported = client.get(f"/api/v1/projects/{project}/export")
        assert exported.status_code == 200, exported.text
        payload = exported.content
        with ZipFile(BytesIO(payload)) as archive:
            assert json.loads(archive.read("manifest.json"))["records"][
                "providerRequirements"
            ] == requirements


@pytest.mark.parametrize("field,value", [
    ("assets_snapshot", [{"assetId": "missing-path"}]),
    ("context_snapshot", {"media": [{}]}),
    ("execution_context", {"media": [{}]}),
])
def test_malformed_history_upload_is_rejected_without_publication(client, field, value):
    container = client.app.state.container
    project = _project(client)["id"]
    task = _task(client, project, "History", "Prompt")["id"]
    generation = container.generation_service
    generation.attach_queue(HeldQueue())
    submitted = client.post(f"/api/v1/projects/{project}/tasks/{task}/generation", json={})
    assert submitted.status_code == 202, submitted.text
    client.portal.call(generation.execute, submitted.json()["id"])
    exported = client.get(f"/api/v1/projects/{project}/export")
    assert exported.status_code == 200, exported.text
    damaged = BytesIO()
    with ZipFile(BytesIO(exported.content)) as original, ZipFile(damaged, "w") as changed:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "manifest.json":
                manifest = json.loads(data)
                manifest["records"]["jobs"][0][field] = value
                data = json.dumps(manifest).encode("utf-8")
            changed.writestr(entry, data)
    before = client.get("/api/v1/projects").json()
    storage = container.file_library.storage
    staging = storage.managed.resolve("staging")
    objects = storage.managed.resolve("objects")
    before_objects = {path.relative_to(objects) for path in objects.rglob("*") if path.is_file()}
    response = client.post("/api/v1/projects/import", files={
        "file": ("damaged-history.zip", damaged.getvalue(), "application/zip"),
    })
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PROJECT_TRANSFER_RECORDS_INVALID"
    assert client.get("/api/v1/projects").json() == before
    after_objects = {path.relative_to(objects) for path in objects.rglob("*") if path.is_file()}
    assert after_objects == before_objects
    assert not list(staging.glob("shotmill-import-*"))
