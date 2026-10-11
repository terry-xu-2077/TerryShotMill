from pathlib import Path

from fastapi.testclient import TestClient

from shotmill.app_factory import create_app
from shotmill.config import Settings
from test_prompt_batch_recovery import HeldQueue


def test_local_file_is_shared_by_reference_and_result_lives_beside_document(
    tmp_path, providers,
):
    source = tmp_path / "original.png"
    source.write_bytes(b"original-media")
    data = tmp_path / "app"
    settings = Settings(
        app_name="ShotMill", api_version="0.3", data_root=data,
        database_url=f"sqlite+pysqlite:///{(data / 'unused.db').as_posix()}",
    )
    paths = [tmp_path / "one" / "one.shotmill", tmp_path / "two" / "two.shotmill"]
    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as client:
        container = client.app.state.container
        container.generation_service.attach_queue(HeldQueue())
        project_ids = []
        asset_ids = []
        for index, path in enumerate(paths):
            response = client.post("/api/v1/projects", json={
                "title": f"Project {index}", "path": str(path),
            })
            assert response.status_code == 201, response.text
            project_id = response.json()["id"]
            project_ids.append(project_id)
            if index == 0:
                imported = client.post(f"/api/v1/projects/{project_id}/assets/local", json={
                    "path": str(source), "name": "Shared original",
                })
            else:
                imported = client.post(f"/api/v1/projects/{project_id}/assets/import", json={
                    "sources": [{"kind": "asset", "id": asset_ids[0]}],
                })
            assert imported.status_code == 201, imported.text
            asset = imported.json() if index == 0 else imported.json()[0]
            asset_ids.append(asset["id"])
            assert client.get(asset["thumbnailUrl"]).content == source.read_bytes()
            assert len(container.project_documents.paths) == index + 1
        assert not list((data / "files" / "objects").rglob("*"))
        assert paths[0].is_file() and paths[1].is_file()

        project_id, asset_id = project_ids[1], asset_ids[1]
        task_response = client.post(f"/api/v1/projects/{project_id}/tasks", json={
            "title": "Shot", "userPrompt": "Original shot", "promptSource": "user",
            "durationSeconds": 6,
            "generation": {"resolution": "1080p", "quality": "标准",
                           "mode": "全能参考", "contextMode": "不承接"},
            "assetBindings": [{"assetId": asset_id, "reference": "<Picture 1>"}],
        })
        assert task_response.status_code == 201, task_response.text
        task_id = task_response.json()["id"]
        preview = client.post(f"/api/v1/projects/{project_id}/prompt-enhancement-previews",
                              json={
            "target": "minimax-h3", "userPrompt": "Original shot",
            "media": [{"assetId": asset_id, "reference": "<Picture 1>"}],
            "generation": {"durationSeconds": 6, "mode": "全能参考"},
        })
        assert preview.status_code == 200, preview.text
        assert providers[0].requests[-1].media[0].path == source
        submitted = client.post(
            f"/api/v1/projects/{project_id}/tasks/{task_id}/generation", json={},
        )
        assert submitted.status_code == 202, submitted.text
        client.portal.call(container.generation_service.execute, submitted.json()["id"])
        assert providers[1].requests[-1].assets[0].path == source
        with container.generation_service.uow_factory() as uow:
            results = uow.results.list_by_task(task_id)
        assert len(results) == 1
        result = results[0]
        relative = result.video_url.split(f"/media/{project_id}/", 1)[1]
        output = container.project_documents.media_root(project_id) / Path(relative)
        assert output.is_file() and output.read_bytes() == b"fake-video-bytes"
        assert client.get(result.video_url).content == b"fake-video-bytes"
        second = client.post(
            f"/api/v1/projects/{project_id}/tasks/{task_id}/generation", json={},
        )
        assert second.status_code == 202, second.text
        client.portal.call(container.generation_service.execute, second.json()["id"])
        with container.generation_service.uow_factory() as uow:
            versions = uow.results.list_by_task(task_id)
        assert len(versions) == 2
        assert versions[0].video_url != versions[1].video_url
        assert output.read_bytes() == b"fake-video-bytes"

        removed = client.delete(f"/api/v1/projects/{project_ids[0]}/assets/{asset_ids[0]}")
        assert removed.status_code == 204, removed.text
        assert source.read_bytes() == b"original-media"
        assert client.get(f"/media/{project_id}/external/asset/{asset_id}/content").status_code == 200

    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as reopened:
        assert reopened.get(result.video_url).content == b"fake-video-bytes"
        assert reopened.get(
            f"/media/{project_id}/external/asset/{asset_id}/content"
        ).content == b"original-media"
        assert reopened.get(f"/api/v1/projects/{project_id}/workspace").status_code == 200
        source.unlink()
        missing = reopened.get(f"/media/{project_id}/external/asset/{asset_id}/content")
        assert missing.status_code == 404
        preview = reopened.post(f"/api/v1/projects/{project_id}/prompt-enhancement-previews",
                                json={
            "target": "minimax-h3", "userPrompt": "Original shot",
            "media": [{"assetId": asset_id, "reference": "<Picture 1>"}],
            "generation": {"durationSeconds": 6, "mode": "全能参考"},
        })
        assert preview.status_code == 404
    assert not (data / "unused.db").exists()
