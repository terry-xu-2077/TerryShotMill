import pytest


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("source", ["user", "ai"])
@pytest.mark.parametrize("stale_review", [False, True])
def test_generation_uses_current_prompt_without_enhancement_or_review(
    client, batch, source, stale_review,
):
    project = client.post("/api/v1/projects", json={"title": "直接生成"}).json()
    route = f"/api/v1/projects/{project['id']}"
    payload = {
        "title": "镜头", "userPrompt": "用户原文", "aiEnhancedPrompt": "已有 AI 文本",
        "promptSource": source, "durationSeconds": 6,
        "generation": {"contextMode": "不承接"},
    }
    task = client.post(f"{route}/tasks", json=payload).json()
    if stale_review:
        assert client.post(f"{route}/tasks/{task['id']}/prompt-review").status_code == 200
        payload["userPrompt" if source == "user" else "aiEnhancedPrompt"] = "修改后当前文本"
        assert client.patch(f"{route}/tasks/{task['id']}", json=payload).status_code == 200

    class HeldQueue:
        async def enqueue(self, job_id):
            pass

    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    if batch:
        body = {"taskIds": [task["id"]]}
        preview = client.post(f"{route}/video-generation-batches/eligibility", json=body)
        assert preview.json()["eligibleTaskIds"] == [task["id"]]
        response = client.post(f"{route}/video-generation-batches", json=body)
        assert response.json()["eligibleTaskIds"] == [task["id"]]
    else:
        response = client.post(f"{route}/tasks/{task['id']}/generation", json={})
    assert response.status_code == 202, response.text
    with service.uow_factory() as uow:
        jobs = uow.jobs.list_by_task(task["id"])
        assert len(jobs) == 1
        expected = payload["userPrompt" if source == "user" else "aiEnhancedPrompt"]
        assert jobs[0].final_prompt_snapshot == expected
        assert uow.tasks.get(task["id"]).approved_prompt_hash is None
    duplicate = client.post(f"{route}/video-generation-batches", json={"taskIds": [task["id"]]})
    assert duplicate.json()["eligibleTaskIds"] == []
    assert duplicate.json()["skipped"][0]["reason"] == "busy"
