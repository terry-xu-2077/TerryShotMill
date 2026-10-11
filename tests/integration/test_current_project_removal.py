import json

from shotmill.domain.entities import Job
from shotmill.domain.enums import JobStatus


def test_direct_task_delete_and_project_removal_keep_the_engineering_file(client, tmp_path):
    project_file = tmp_path / "working.shotmill"
    created = client.post("/api/v1/projects", json={"title": "工作工程", "path": str(project_file)})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    base = f"/api/v1/projects/{project_id}"
    task = client.post(f"{base}/tasks", json={"title": "片段"})
    assert task.status_code == 201, task.text
    removed = client.post(f"{base}/tasks/delete", json={"taskIds": [task.json()["id"]]})
    assert removed.status_code == 200, removed.text
    assert removed.json()["deletedIds"] == [task.json()["id"]]
    assert client.get(f"{base}/workspace").json()["tasks"] == []
    assert project_file.is_file()
    forgotten = client.delete(base)
    assert forgotten.status_code == 204, forgotten.text
    assert project_file.is_file()
    assert all(item["id"] != project_id for item in client.get("/api/v1/projects").json()["items"])
    assert client.post("/api/v1/projects/open", json={"path": str(project_file)}).status_code == 200
    assert client.post(f"{base}/lifecycle", json={"action": "trash"}).status_code == 404
    assert client.get("/api/v1/result-archive").status_code == 404


def test_current_engineering_file_drops_retired_archive_metadata_on_save(client, tmp_path):
    path = tmp_path / "current.shotmill"
    project = client.post("/api/v1/projects", json={"title": "保留工程", "path": str(path)}).json()
    project_id = project["id"]
    task = client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "保留片段"}).json()
    assert client.delete(f"/api/v1/projects/{project_id}").status_code == 204
    document = json.loads(path.read_text(encoding="utf-8"))
    document["tables"]["archived_results"] = []
    document["tables"]["pending_file_cleanup"] = []
    document["tables"]["projects"][0].update(archived_at=None, deleted_at=None)
    document["tables"]["generation_tasks"][0].update(archived_at=None, deleted_at=None)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    reopened = client.post("/api/v1/projects/open", json={"path": str(path)})
    assert reopened.status_code == 200, reopened.text
    workspace = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert [item["id"] for item in workspace["tasks"]] == [task["id"]]
    assert client.patch(f"/api/v1/projects/{project_id}", json={"description": "继续编辑"}).status_code == 200
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "archived_results" not in saved["tables"]
    assert "pending_file_cleanup" not in saved["tables"]
    assert "archived_at" not in saved["tables"]["projects"][0]


def test_direct_removal_keeps_original_media_and_refuses_active_job(client, tmp_path):
    source = tmp_path / "original.png"
    source.write_bytes(b"user-original")
    path = tmp_path / "with-media.shotmill"
    project_id = client.post("/api/v1/projects", json={
        "title": "素材工程", "path": str(path),
    }).json()["id"]
    base = f"/api/v1/projects/{project_id}"
    imported = client.post(f"{base}/assets/local", json={"path": str(source)})
    assert imported.status_code == 201, imported.text
    asset_id = imported.json()["id"]
    task = client.post(f"{base}/tasks", json={
        "title": "引用素材", "assetBindings": [{"assetId": asset_id, "reference": "<Picture 1>"}],
    })
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    container = client.app.state.container
    with container.generation_service.uow_factory() as uow:
        uow.jobs.add(Job(
            id="running-test-job", project_id=project_id, task_id=task_id,
            status=JobStatus.QUEUED, final_prompt_snapshot="", task_content_snapshot={},
            assets_snapshot=[], generation_profile_snapshot={}, provider_profile_snapshot={},
            params_snapshot={}, context_snapshot={},
        ))
    assert client.post(f"{base}/tasks/delete", json={"taskIds": [task_id]}).status_code == 409
    assert client.delete(base).status_code == 409
    assert path.is_file() and source.read_bytes() == b"user-original"
    with container.generation_service.uow_factory() as uow:
        job = uow.jobs.get("running-test-job")
        job.status = JobStatus.CANCELLED
        uow.jobs.update_runtime(job)
    assert client.post(f"{base}/tasks/delete", json={"taskIds": [task_id]}).status_code == 200
    assert client.delete(base).status_code == 204
    assert path.is_file() and source.read_bytes() == b"user-original"
