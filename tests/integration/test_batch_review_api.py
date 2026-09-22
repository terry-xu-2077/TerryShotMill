from __future__ import annotations

import time

import pytest


def _project(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "title": "批量生产",
            "description": "夜雨港口的短剧项目",
            "useDescriptionForAiPrompt": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _task(client, project_id: str, title: str, prompt: str):
    response = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": title,
            "summary": title,
            "userIntent": prompt,
            "userPrompt": prompt,
            "promptSource": "user",
            "durationSeconds": 6,
            "generation": {
                "resolution": "1080p",
                "quality": "标准",
                "mode": "全能参考",
                "contextMode": "不承接",
            },
            "assetBindings": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait_job(client, job_id: str):
    deadline = time.time() + 3
    while time.time() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in {"completed", "failed"}:
            return data
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _wait_prompt_batch(client, project_id: str, batch_id: str):
    deadline = time.time() + 3
    latest = None
    while time.time() < deadline:
        response = client.get(
            f"/api/v1/projects/{project_id}/prompt-enhancement-batches/{batch_id}"
        )
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["state"] in {"completed", "partial", "failed", "cancelled"}:
            return latest
        time.sleep(0.02)
    raise AssertionError(f"prompt batch did not finish: {latest}")


def test_batch_prompt_review_then_video_generation(client, providers) -> None:
    prompt_provider, video_provider = providers
    project = _project(client)
    first = _task(client, project["id"], "雨夜码头", "角色在雨夜码头停下脚步")
    second = _task(client, project["id"], "仓库入口", "角色推开旧仓库铁门")

    batch = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches",
        json={
            "taskIds": [first["id"], second["id"]],
            "includeProjectBackground": True,
            "includePreviousTaskSummary": True,
        },
    )
    assert batch.status_code == 202, batch.text
    body = _wait_prompt_batch(client, project["id"], batch.json()["batchId"])
    assert body["state"] == "completed"
    assert [item["state"] for item in body["items"]] == ["completed", "completed"]
    assert len(prompt_provider.requests) == 2
    assert "夜雨港口" in prompt_provider.requests[0].user_text
    assert "雨夜码头" in prompt_provider.requests[1].user_text

    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    assert [task["promptReviewStatus"] for task in workspace["tasks"]] == [
        "pending_review",
        "pending_review",
    ]

    blocked = client.post(
        f"/api/v1/projects/{project['id']}/video-generation-batches/eligibility",
        json={"taskIds": [first["id"], second["id"]]},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["eligibleTaskIds"] == [first["id"], second["id"]]
    assert blocked.json()["skipped"] == []

    approved = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{first['id']}/prompt-review",
        json={"action": "approve"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["promptReviewStatus"] == "approved"

    eligible = client.post(
        f"/api/v1/projects/{project['id']}/video-generation-batches/eligibility",
        json={"taskIds": [first["id"], second["id"]]},
    )
    assert eligible.status_code == 200, eligible.text
    assert eligible.json()["eligibleTaskIds"] == [first["id"], second["id"]]
    assert eligible.json()["skipped"] == []

    submitted = client.post(
        f"/api/v1/projects/{project['id']}/video-generation-batches",
        json={"taskIds": [first["id"], second["id"]]},
    )
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["eligibleTaskIds"] == [first["id"], second["id"]]

    deadline = time.time() + 2
    while len(video_provider.requests) < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert len(video_provider.requests) == 2
    job_id = video_provider.requests[0].job_id
    assert _wait_job(client, job_id)["status"] == "completed"
    assert len(video_provider.requests) == 2

    active = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    assert active["tasks"][0]["hasActiveVideoJob"] is False


def test_prompt_approval_invalidates_when_effective_prompt_changes(client) -> None:
    project = _project(client)
    task = _task(client, project["id"], "码头", "角色站在码头")

    approved = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/prompt-review",
        json={"action": "approve"},
    )
    assert approved.status_code == 200

    editor = client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/editor").json()
    changed = client.patch(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}",
        json={
            "title": editor["title"],
            "summary": editor["summary"],
            "scriptSource": editor["scriptSource"],
            "userIntent": editor["userIntent"],
            "userPrompt": "角色快步穿过码头",
            "aiEnhancedPrompt": editor["aiEnhancedPrompt"],
            "promptSource": "user",
            "durationSeconds": editor["durationSeconds"],
            "generation": {
                **editor["generation"],
                "durationSeconds": editor["durationSeconds"],
            },
            "assetBindings": editor["assetBindings"],
            "editorPreference": {
                "userViewMode": "text",
                "aiViewMode": editor["editorPreference"]["aiViewMode"],
            },
            "revision": editor["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["promptReviewStatus"] == "pending_review"


def test_prompt_approval_survives_view_mode_only_change(client) -> None:
    project = _project(client)
    task = _task(client, project["id"], "码头", "角色站在码头")

    approved = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/prompt-review",
        json={"action": "approve"},
    )
    assert approved.status_code == 200

    editor = client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/editor").json()
    changed = client.patch(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}",
        json={
            "title": editor["title"],
            "summary": editor["summary"],
            "scriptSource": editor["scriptSource"],
            "userIntent": editor["userIntent"],
            "userPrompt": editor["userPrompt"],
            "aiEnhancedPrompt": editor["aiEnhancedPrompt"],
            "promptSource": editor["promptSource"],
            "durationSeconds": editor["durationSeconds"],
            "generation": editor["generation"],
            "assetBindings": editor["assetBindings"],
            "editorPreference": {
                "userViewMode": "text",
                "aiViewMode": "text",
            },
            "revision": editor["revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["promptReviewStatus"] == "approved"


def test_reenhancement_invalidates_existing_prompt_approval(client) -> None:
    project = _project(client)
    task = _task(client, project["id"], "码头", "角色站在码头")

    approved = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/prompt-review",
        json={"action": "approve"},
    )
    assert approved.status_code == 200
    editor = client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/editor").json()

    enhanced = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/prompt-enhancements",
        json={
            "target": "minimax-h3",
            "userPrompt": editor["userPrompt"],
            "media": [],
            "context": {
                "includeProjectBackground": False,
                "includePreviousTaskSummary": False,
            },
            "generation": {
                **editor["generation"],
                "durationSeconds": editor["durationSeconds"],
            },
        },
    )
    assert enhanced.status_code == 201, enhanced.text

    state = client.get(f"/api/v1/projects/{project['id']}/prompt-review-state")
    assert state.status_code == 200
    assert state.json()["items"][0]["promptReviewStatus"] == "pending_review"


def _edit(client, project_id, task_id, **changes):
    route = f"/api/v1/projects/{project_id}/tasks/{task_id}"
    editor = client.get(f"{route}/editor").json()
    fields = (
        "title", "summary", "scriptSource", "userIntent", "userPrompt", "aiEnhancedPrompt",
        "promptSource", "durationSeconds", "generation", "assetBindings", "editorPreference",
        "revision",
    )
    payload = {key: editor[key] for key in fields}
    response = client.patch(route, json={**payload, **changes})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("source", ["user", "ai"])
@pytest.mark.parametrize("change,expected", [
    ("effective-content", "pending_review"),
    ("inactive-content", "approved"),
    ("source", "pending_review"),
    ("view", "approved"),
    ("title", "approved"),
    ("empty", "not_ready"),
])
def test_prompt_review_invalidation_matrix(client, source, change, expected):
    project = _project(client)
    task = _task(client, project["id"], "审核矩阵", "相同的提示词")
    route = f"/api/v1/projects/{project['id']}/tasks/{task['id']}"
    _edit(client, project["id"], task["id"],
          aiEnhancedPrompt="相同的提示词", promptSource=source)
    approved = client.post(f"{route}/prompt-review", json={"action": "approve"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["approvedAt"]
    effective = "userPrompt" if source == "user" else "aiEnhancedPrompt"
    inactive = "aiEnhancedPrompt" if source == "user" else "userPrompt"
    changes = {
        "effective-content": {effective: "内容已经改动"},
        "inactive-content": {inactive: "未使用的提示词改动"},
        "source": {"promptSource": "ai" if source == "user" else "user"},
        "view": {"editorPreference": {"userViewMode": "text", "aiViewMode": "text"}},
        "title": {"title": "仅修改任务名称"},
        "empty": {effective: ""},
    }
    result = _edit(client, project["id"], task["id"], **changes[change])
    assert result["promptReviewStatus"] == expected
    eligibility = client.post(
        f"/api/v1/projects/{project['id']}/video-generation-batches/eligibility",
        json={"taskIds": [task["id"]]},
    ).json()
    assert eligibility["eligibleTaskIds"] == ([task["id"]] if expected != "not_ready" else [])
    if change == "source":
        # Returning to identical previously approved content cannot resurrect approval.
        restored = _edit(client, project["id"], task["id"], promptSource=source)
        assert restored["promptReviewStatus"] == "pending_review"


@pytest.mark.parametrize("source", ["user", "ai"])
def test_selecting_another_ai_revision_invalidates_review_even_with_identical_text(client, source):
    project = _project(client)
    task = _task(client, project["id"], "版本审核", "角色站在码头")
    route = f"/api/v1/projects/{project['id']}/tasks/{task['id']}"
    revisions = []
    for _ in range(2):
        enhanced = client.post(f"{route}/prompt-enhancements", json={
            "target": "minimax-h3", "userPrompt": "角色站在码头", "media": [],
            "context": {"includeProjectBackground": False, "includePreviousTaskSummary": False},
            "generation": {"durationSeconds": 6, "mode": "全能参考", "contextMode": "不承接"},
        })
        assert enhanced.status_code == 201, enhanced.text
        revisions.append(enhanced.json())
    assert revisions[0]["prompt"] == revisions[1]["prompt"]
    _edit(client, project["id"], task["id"], promptSource=source)
    assert client.post(f"{route}/prompt-review", json={"action": "approve"}).status_code == 200
    selected = client.post(f"{route}/prompt-revisions/{revisions[0]['id']}/select")
    assert selected.status_code == 200, selected.text
    state = client.get(f"/api/v1/projects/{project['id']}/prompt-review-state").json()
    assert state["items"][0]["promptReviewStatus"] == "pending_review"
    assert state["items"][0]["approvedAt"] is None
