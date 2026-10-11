from fastapi.testclient import TestClient

from shotmill.app_factory import create_app
from shotmill.config import Settings


def test_timelines_group_tasks_in_the_project_file(tmp_path, providers):
    project_file = tmp_path / "film.shotmill"
    settings = Settings(app_name="ShotMill", api_version="0.3", data_root=tmp_path / "app",
                        database_url="sqlite+pysqlite:///:memory:")
    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as client:
        created = client.post("/api/v1/projects", json={"title": "Film", "path": str(project_file)})
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        base = f"/api/v1/projects/{project_id}"
        first = client.post(f"{base}/timelines", json={"title": "开场"})
        second = client.post(f"{base}/timelines", json={"title": "结尾"})
        assert first.status_code == second.status_code == 201
        first_id, second_id = first.json()["id"], second.json()["id"]
        task_ids = []
        for timeline_id, title in ((first_id, "镜头 A"), (second_id, "镜头 B")):
            task = client.post(f"{base}/tasks", json={
                "title": title, "timelineId": timeline_id,
                "userPrompt": title, "generation": {"contextMode": "不承接"},
            })
            assert task.status_code == 201, task.text
            task_ids.append(task.json()["id"])
        changed = client.patch(f"{base}/tasks/{task_ids[1]}", json={
            "title": "镜头 B", "userPrompt": "镜头 B", "generation": {"contextMode": "尾帧承接"},
        })
        assert changed.status_code == 200, changed.text
        with client.app.state.container.task_service.uow_factory() as uow:
            assert uow.contexts.list_by_target(task_ids[1]) == []
        workspace = client.get(f"{base}/workspace").json()
        assert [item["title"] for item in workspace["timelines"]] == ["开场", "结尾"]
        assert [len(item["taskIds"]) for item in workspace["timelines"]] == [1, 1]
        assert client.delete(f"{base}/timelines/{first_id}").status_code == 409
        assert client.patch(f"{base}/timelines/{second_id}", json={"title": "尾声"}).status_code == 200
        empty = client.post(f"{base}/timelines", json={"title": "临时"}).json()["id"]
        assert client.delete(f"{base}/timelines/{empty}").status_code == 204
        assert client.post(f"{base}/tasks", json={"title": "Bad", "timelineId": "missing"}).status_code == 404

    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as reopened:
        assert reopened.post("/api/v1/projects/open", json={"path": str(project_file)}).status_code == 200
        timelines = reopened.get(f"/api/v1/projects/{project_id}/workspace").json()["timelines"]
        assert [item["title"] for item in timelines] == ["开场", "尾声"]
        assert [len(item["taskIds"]) for item in timelines] == [1, 1]
