from datetime import UTC, datetime

from shotmill.domain.entities import AiPromptRevision


def test_workspace_reports_latest_enhancement_without_changing_prompt_source(client):
    project = client.post("/api/v1/projects", json={"title": "New results"}).json()
    route = f"/api/v1/projects/{project['id']}"
    task = client.post(f"{route}/tasks", json={
        "title": "Task", "userPrompt": "Original", "promptSource": "user",
        "durationSeconds": 6, "generation": {"contextMode": "不承接"},
    }).json()
    assert task["latestPromptRevisionId"] is None
    with client.app.state.container.workspace_query.uow_factory() as uow:
        for index in [2, 1]:
            uow.prompt_revisions.add(AiPromptRevision(
                id=f"revision-{index}", project_id=project["id"], task_id=task["id"],
                source_user_prompt="Original", output_prompt="Enhanced", asset_ids=[],
                project_background_used=False, previous_task_summary_used=False,
                target_skill="test", skill_version="1",
                created_at=datetime(2026, 1, index, tzinfo=UTC),
            ))
        uow.commit()
    summary = client.get(f"{route}/workspace").json()["tasks"][0]
    assert summary["latestPromptRevisionId"] == "revision-2"
    assert summary["latestVideoResultId"] is None
    assert summary["promptExcerpt"] == "Original"
