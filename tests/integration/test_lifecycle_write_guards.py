import pytest


@pytest.mark.parametrize("scope", ["project", "task"])
@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("operation", [
    "edit", "preference", "review", "revision", "primary", "generate", "enhance",
])
def test_readonly_task_write_routes(client, scope, action, operation):
    project = client.post("/api/v1/projects", json={"title": "只读保护"}).json()
    base = f"/api/v1/projects/{project['id']}"
    task = client.post(f"{base}/tasks", json={"title": "原任务", "userPrompt": "原提示词"}).json()
    task_path = f"{base}/tasks/{task['id']}"
    path, payload = (f"{base}/lifecycle", {"action": action}) if scope == "project" else (
        f"{base}/tasks/lifecycle", {"action": action, "taskIds": [task["id"]]},
    )
    assert client.post(path, json=payload).status_code == 200
    operations = {
        "edit": ("PATCH", task_path, {"title": "不应保存"}),
        "preference": ("PATCH", f"{task_path}/editor-preference", {"userViewMode": "text"}),
        "review": ("POST", f"{task_path}/prompt-review", {}),
        "revision": ("POST", f"{task_path}/prompt-revisions/missing/select", {}),
        "primary": ("PATCH", f"{task_path}/primary-result", {"resultId": "missing"}),
        "generate": ("POST", f"{task_path}/generation", {}),
        "enhance": ("POST", f"{task_path}/prompt-enhancements", {
            "target": "minimax-h3", "userPrompt": "原提示词",
            "generation": {"durationSeconds": 6, "mode": "全能参考"},
        }),
    }
    method, url, body = operations[operation]
    response = client.request(method, url, json=body)
    assert response.status_code == 409, response.text
    assert "OBJECT_READ_ONLY" in response.text
    with client.app.state.container.task_service.uow_factory() as uow:
        stored = uow.tasks.get(task["id"])
        assert stored.title == "原任务"
        assert stored.user_view_mode == "visual"
        assert stored.approved_at is None
        assert uow.jobs.active_task_ids_by_project(project["id"]) == set()
        assert uow.prompt_jobs.active_task_ids_by_project(project["id"]) == set()
        assert uow.prompt_jobs.list_by_task(task["id"]) == []


@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("operation", [
    "project", "create", "reorder", "asset-edit", "asset-delete", "asset-upload", "import",
    "preview",
])
def test_readonly_project_write_routes(client, action, operation):
    project = client.post("/api/v1/projects", json={"title": "原项目"}).json()
    base = f"/api/v1/projects/{project['id']}"
    asset_response = client.post(f"{base}/assets", files={
        "file": ("original.txt", b"original", "text/plain"),
    })
    assert asset_response.status_code == 201
    asset = asset_response.json()
    assert client.post(f"{base}/lifecycle", json={"action": action}).status_code == 200
    operations = {
        "project": ("PATCH", base, {"title": "不应保存"}),
        "create": ("POST", f"{base}/tasks", {"title": "新任务"}),
        "reorder": ("POST", f"{base}/tasks/reorder", {"taskIds": []}),
        "asset-edit": ("PATCH", f"{base}/assets/{asset['id']}", {"name": "不应保存"}),
        "asset-delete": ("DELETE", f"{base}/assets/{asset['id']}", {}),
        "import": ("POST", f"{base}/assets/import", {
            "sources": [{"kind": "asset", "id": "missing"}],
        }),
        "preview": ("POST", f"{base}/prompt-enhancement-previews", {
            "target": "minimax-h3", "userPrompt": "提示词",
            "generation": {"durationSeconds": 6, "mode": "全能参考"},
        }),
    }
    if operation == "asset-upload":
        response = client.post(f"{base}/assets", files={"file": ("new.txt", b"new")})
    else:
        method, url, body = operations[operation]
        response = client.request(method, url, json=body)
    assert response.status_code == 409, response.text
    assert "OBJECT_READ_ONLY" in response.text
    assert client.get(f"{base}/assets").json()["items"] == [asset]


@pytest.mark.parametrize("scope", ["project", "task"])
@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("kind", ["prompt", "video"])
def test_readonly_batch_routes_do_not_execute(client, scope, action, kind):
    project = client.post("/api/v1/projects", json={"title": "批量只读"}).json()
    base = f"/api/v1/projects/{project['id']}"
    task = client.post(f"{base}/tasks", json={
        "title": "原任务", "userPrompt": "原提示词", "promptSource": "user",
    }).json()
    path, payload = (f"{base}/lifecycle", {"action": action}) if scope == "project" else (
        f"{base}/tasks/lifecycle", {"action": action, "taskIds": [task["id"]]},
    )
    assert client.post(path, json=payload).status_code == 200
    endpoint = "prompt-enhancement-batches" if kind == "prompt" else "video-generation-batches"
    response = client.post(f"{base}/{endpoint}", json={"taskIds": [task["id"]]})
    if kind == "prompt" and scope == "project":
        assert response.status_code == 409, response.text
        assert "OBJECT_READ_ONLY" in response.text
    else:
        assert response.status_code == 202, response.text
        body = response.json()
        if kind == "prompt":
            assert [(item["taskId"], item["state"]) for item in body["items"]] == [
                (task["id"], "skipped"),
            ]
        else:
            assert body["eligibleTaskIds"] == []
            assert [(item["taskId"], item["code"]) for item in body["skipped"]] == [
                (task["id"], "OBJECT_READ_ONLY"),
            ]
    with client.app.state.container.task_service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task["id"]) == []
        assert uow.prompt_revisions.list_by_task(task["id"]) == []
        assert uow.prompt_jobs.active_task_ids_by_project(project["id"]) == set()
