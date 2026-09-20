from __future__ import annotations


def _create_project(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "异星边境",
            "description": "荒漠殖民地",
            "useDescriptionForAiPrompt": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task(client, project_id: str, **overrides):
    payload = {
        "title": "越野车飞跃断层",
        "userPrompt": "越野车高速冲向断层并飞跃过去",
        "promptSource": "user",
        "durationSeconds": 6,
        "generation": {
            "resolution": "1080p",
            "quality": "标准",
            "mode": "全能参考",
            "contextMode": "不承接",
        },
        "assetBindings": [],
    }
    payload.update(overrides)
    response = client.post(f"/api/v1/projects/{project_id}/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_project_workspace_and_task_editor_contract(client) -> None:
    project = _create_project(client)
    task = _create_task(client, project["id"])

    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace")
    assert workspace.status_code == 200
    body = workspace.json()
    assert body["project"]["title"] == "异星边境"
    assert body["tasks"][0]["id"] == task["id"]
    assert body["tasks"][0]["promptExcerpt"].startswith("越野车")
    assert "provider" not in str(body).lower()
    assert "absolute" not in str(body).lower()

    editor = client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/editor")
    assert editor.status_code == 200
    data = editor.json()
    assert data["promptSource"] == "user"
    assert data["userPrompt"].startswith("越野车")
    assert data["finalPrompt"] == data["userPrompt"]
    assert data["revision"] == 1


def test_selected_workflow_survives_task_save_and_editor_reload(client) -> None:
    project = _create_project(client)
    task = _create_task(client, project["id"], generation={
        "workflowProfileId": "configured-detail", "contextMode": "不承接",
    }, durationSeconds=12)
    url = f"/api/v1/projects/{project['id']}/tasks/{task['id']}"
    editor = client.get(f"{url}/editor").json()
    assert editor["generation"]["workflowProfileId"] == "configured-detail"
    assert editor["durationSeconds"] == 12
    updated = client.patch(url, json={
        "title": task["title"], "userPrompt": editor["userPrompt"],
        "promptSource": "user", "durationSeconds": 8,
        "generation": {**editor["generation"], "workflowProfileId": "configured-standard"},
        "revision": editor["revision"],
    })
    assert updated.status_code == 200, updated.text
    reloaded = client.get(f"{url}/editor").json()
    assert reloaded["generation"]["workflowProfileId"] == "configured-standard"
    assert reloaded["durationSeconds"] == 8


def test_task_optimistic_lock_and_reorder(client) -> None:
    project = _create_project(client)
    first = _create_task(client, project["id"], title="A")
    second = _create_task(client, project["id"], title="B")

    reorder = client.post(
        f"/api/v1/projects/{project['id']}/tasks/reorder",
        json={"taskIds": [second["id"], first["id"]]},
    )
    assert reorder.status_code == 204, reorder.text
    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    assert [item["title"] for item in workspace["tasks"]] == ["B", "A"]

    editor = client.get(f"/api/v1/projects/{project['id']}/tasks/{first['id']}/editor").json()
    stale = client.patch(
        f"/api/v1/projects/{project['id']}/tasks/{first['id']}",
        json={
            "title": "A changed",
            "userPrompt": "new",
            "promptSource": "user",
            "durationSeconds": 6,
            "generation": {"contextMode": "不承接"},
            "revision": editor["revision"] - 1,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "TASK_CONFLICT"


def test_optional_workflow_slots_survive_save_and_reload(client) -> None:
    project = _create_project(client)
    selection = {"workflowId": "reference.json", "slots": [
        {"portId": "9:image_0:1", "assetId": None, "reference": "<Picture 1>"},
        {"portId": "9:audio_0:4", "assetId": None, "reference": "<Audio 1>"},
    ]}
    task = _create_task(client, project["id"], generation={
        "workflowInputs": selection, "contextMode": "不承接",
    })
    url = f"/api/v1/projects/{project['id']}/tasks/{task['id']}/editor"
    assert client.get(url).json()["generation"]["workflowInputs"] == selection
