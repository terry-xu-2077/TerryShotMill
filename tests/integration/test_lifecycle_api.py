import asyncio


def test_project_lifecycle_and_edit_guard(client):
    project = client.post("/api/v1/projects", json={"title": "Lifecycle"}).json()
    path = f"/api/v1/projects/{project['id']}"
    response = client.post(f"{path}/lifecycle", json={"action": "archive"})
    assert response.status_code == 200
    assert response.json()["archivedAt"] is not None
    assert client.get("/api/v1/projects").json()["items"] == []
    archived = client.get("/api/v1/projects?scope=archived").json()["items"]
    assert [item["id"] for item in archived] == [project["id"]]
    assert archived[0]["archivedAt"] is not None
    assert client.patch(path, json={"title": "Changed"}).status_code == 409
    assert client.post(f"{path}/lifecycle", json={"action": "trash"}).status_code == 200
    assert client.get("/api/v1/projects?scope=archived").json()["items"] == []
    assert len(client.get("/api/v1/projects?scope=trash").json()["items"]) == 1
    restored = client.post(f"{path}/lifecycle", json={"action": "restore"}).json()
    assert restored["deletedAt"] is None
    assert restored["archivedAt"] is not None
    assert client.post(f"{path}/lifecycle", json={"action": "unarchive"}).status_code == 200
    assert client.patch(path, json={"title": "Changed"}).status_code == 200
    assert client.post(f"{path}/lifecycle", json={"action": "purge"}).status_code == 422


def test_task_lifecycle_selection_validation(client):
    project = client.post("/api/v1/projects", json={"title": "Lifecycle"}).json()
    path = f"/api/v1/projects/{project['id']}/tasks"
    assert client.post(f"{path}/lifecycle", json={
        "taskIds": [], "action": "trash",
    }).status_code == 422
    assert client.post(f"{path}/deletion-preview", json={
        "taskIds": ["missing"],
    }).status_code == 404


def test_batch_lifecycle_roundtrip_and_purge_preserve_unselected_task(client):
    project = client.post("/api/v1/projects", json={"title": "Batch lifecycle"}).json()
    base = f"/api/v1/projects/{project['id']}"
    ids = [client.post(f"{base}/tasks", json={"title": str(index)}).json()["id"]
           for index in range(3)]
    selected = ids[:2]
    for invalid in ([ids[0], ids[0]], [ids[0], "missing"]):
        response = client.post(f"{base}/tasks/lifecycle", json={
            "taskIds": invalid, "action": "trash",
        })
        assert response.status_code in {404, 422}
        assert len(client.get(f"{base}/workspace").json()["tasks"]) == 3
    for action, scope in (
        ("archive", "archived"), ("unarchive", "active"),
        ("trash", "trash"), ("restore", "active"), ("trash", "trash"),
    ):
        response = client.post(f"{base}/tasks/lifecycle", json={
            "taskIds": selected, "action": action,
        })
        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()} == set(selected)
        actual = {item["id"] for item in
                  client.get(f"{base}/workspace?scope={scope}").json()["tasks"]}
        assert actual == (set(ids) if scope == "active" else set(selected))
    response = client.post(f"{base}/tasks/permanent-delete", json={
        "taskIds": selected, "confirmed": True,
    })
    assert response.status_code == 200, response.text
    assert set(response.json()["deletedIds"]) == set(selected)
    assert client.get(f"{base}/workspace?scope=trash").json()["tasks"] == []
    assert [item["id"] for item in client.get(f"{base}/workspace").json()["tasks"]] == ids[2:]


def test_task_archive_trash_restore_workspace_scopes(client):
    project = client.post("/api/v1/projects", json={"title": "Lifecycle"}).json()
    base = f"/api/v1/projects/{project['id']}"
    created = client.post(f"{base}/tasks", json={"title": "Keep history"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    def transition(action):
        response = client.post(f"{base}/tasks/lifecycle", json={
            "taskIds": [task_id], "action": action,
        })
        assert response.status_code == 200

    transition("archive")
    assert client.get(f"{base}/workspace").json()["tasks"] == []
    archived = client.get(f"{base}/workspace?scope=archived").json()["tasks"]
    assert [task["id"] for task in archived] == [task_id]
    assert archived[0]["archivedAt"] is not None
    assert client.patch(f"{base}/tasks/{task_id}", json={"title": "No"}).status_code == 409
    transition("trash")
    assert client.get(f"{base}/workspace?scope=archived").json()["tasks"] == []
    assert len(client.get(f"{base}/workspace?scope=trash").json()["tasks"]) == 1
    transition("restore")
    assert len(client.get(f"{base}/workspace?scope=archived").json()["tasks"]) == 1
    transition("unarchive")
    assert len(client.get(f"{base}/workspace").json()["tasks"]) == 1
    assert client.patch(f"{base}/tasks/{task_id}", json={"title": "Yes"}).status_code == 200


def test_prompt_batch_reports_archived_tasks_as_skipped(client):
    project = client.post("/api/v1/projects", json={"title": "Mixed"}).json()
    base = f"/api/v1/projects/{project['id']}"
    ids = [client.post(f"{base}/tasks", json={
        "title": title, "userPrompt": "A scene",
    }).json()["id"] for title in ("Archived", "Active")]
    assert client.post(f"{base}/tasks/lifecycle", json={
        "taskIds": ids[:1], "action": "archive",
    }).status_code == 200
    service = client.app.state.container.batch_production_service
    result = asyncio.run(service.create_prompt_batch(
        project["id"], task_ids=ids, include_project_background=False,
        include_previous_task_summary=False, enqueue=False,
    ))
    assert [(item.task_id, item.state) for item in result.items] == [
        (ids[0], "skipped"), (ids[1], "queued"),
    ]
