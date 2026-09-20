from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from shotmill.devtools.mock_api import create_mock_app


def test_mock_api_serves_a_stateful_frontend_scenario(tmp_path) -> None:
    application = asyncio.run(create_mock_app(tmp_path / "mock-api"))

    with TestClient(application) as client:
        projects = client.get("/api/v1/projects").json()["items"]
        assert len(projects) == 1
        assert projects[0]["title"] == "雨夜仓库 · Mock 项目"
        assert projects[0]["taskCount"] == 3
        assert projects[0]["assetCount"] == 2

        project_id = projects[0]["id"]
        workspace = client.get(f"/api/v1/projects/{project_id}/workspace").json()
        assert [item["title"] for item in workspace["tasks"]] == [
            "抵达仓库",
            "推门进入",
            "待补充任务",
        ]

        assets = client.get(f"/api/v1/projects/{project_id}/assets").json()["items"]
        assert {item["category"] for item in assets} == {"character", "scene"}
        assert all(item["thumbnailUrl"].startswith("/media/") for item in assets)

        task_id = workspace["tasks"][1]["id"]
        editor = client.get(
            f"/api/v1/projects/{project_id}/tasks/{task_id}/editor"
        ).json()
        assert editor["promptSource"] == "ai"
        assert editor["aiEnhancedPrompt"]

        revisions = client.get(
            f"/api/v1/projects/{project_id}/tasks/{task_id}/prompt-revisions"
        ).json()["items"]
        assert len(revisions) == 1
        assert revisions[0]["providerId"] == "shotmill-mock-prompt"


def test_mock_api_exercises_batch_review_product_flow(tmp_path) -> None:
    application = asyncio.run(create_mock_app(tmp_path / "mock-batch"))

    with TestClient(application) as client:
        project_id = client.get("/api/v1/projects").json()["items"][0]["id"]
        tasks = client.get(f"/api/v1/projects/{project_id}/workspace").json()["tasks"]
        task_ids = [item["id"] for item in tasks[:2]]

        batch = client.post(
            f"/api/v1/projects/{project_id}/prompt-enhancement-batches",
            json={
                "taskIds": task_ids,
                "includeProjectBackground": True,
                "includePreviousTaskSummary": True,
            },
        )
        assert batch.status_code == 202
        assert batch.json()["state"] == "completed"
        assert [item["state"] for item in batch.json()["items"]] == ["completed", "completed"]

        review_state = client.get(
            f"/api/v1/projects/{project_id}/prompt-review-state"
        ).json()["items"]
        assert all(item["promptReviewStatus"] == "pending_review" for item in review_state)

        approved = client.post(
            f"/api/v1/projects/{project_id}/tasks/{task_ids[0]}/prompt-review",
            json={"action": "approve"},
        )
        assert approved.status_code == 200
        assert approved.json()["promptReviewStatus"] == "approved"

        eligibility = client.post(
            f"/api/v1/projects/{project_id}/video-generation-batches/eligibility",
            json={"taskIds": task_ids},
        ).json()
        assert eligibility["eligibleTaskIds"] == [task_ids[0]]
        assert eligibility["skipped"] == [{"taskId": task_ids[1], "reason": "not-reviewed"}]

        submitted = client.post(
            f"/api/v1/projects/{project_id}/video-generation-batches",
            json={"taskIds": task_ids},
        ).json()
        assert submitted["eligibleTaskIds"] == [task_ids[0]]
        assert submitted["batchId"].startswith("videobatch-")


def test_mock_api_keeps_real_contract_and_may_lead_with_target_routes(tmp_path) -> None:
    from shotmill.app import create_app as create_real_app

    mock_schema = asyncio.run(create_mock_app(tmp_path / "mock-api")).openapi()
    real_schema = create_real_app().openapi()

    assert set(real_schema["paths"]).issubset(set(mock_schema["paths"]))
    for path, definition in real_schema["paths"].items():
        assert mock_schema["paths"][path] == definition
    for name, definition in real_schema["components"]["schemas"].items():
        assert mock_schema["components"]["schemas"][name] == definition

    assert "/api/v1/projects/{project_id}/prompt-enhancement-batches" in mock_schema["paths"]
    assert "/api/v1/projects/{project_id}/tasks/{task_id}/prompt-review" in mock_schema["paths"]
    assert (
        "/api/v1/projects/{project_id}/video-generation-batches/eligibility"
        in mock_schema["paths"]
    )
