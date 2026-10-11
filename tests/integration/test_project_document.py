from fastapi.testclient import TestClient
import pytest

from shotmill.app_factory import create_app
from shotmill.config import Settings
from shotmill.domain.entities import (
    AiPromptRevision, ContextLink, Job, Result, Task,
)
from shotmill.domain.enums import JobStatus


def test_document_is_only_project_truth_and_settings_stay_separate(tmp_path, providers):
    data = tmp_path / "app"
    project_file = tmp_path / "chosen" / "film.shotmill"
    settings = Settings(
        app_name="ShotMill", api_version="0.3", data_root=data,
        database_url=f"sqlite+pysqlite:///{(data / 'unused.db').as_posix()}",
    )
    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as client:
        response = client.post("/api/v1/projects", json={
            "title": "Film", "path": str(project_file),
        })
        assert response.status_code == 201, response.text
        project_id = response.json()["id"]
        original = project_file.read_bytes()
        duplicate = client.post("/api/v1/projects", json={
            "title": "Other", "path": str(project_file),
        })
        assert duplicate.status_code == 422
        assert project_file.read_bytes() == original
        container = client.app.state.container
        with container.generation_service.uow_factory() as uow:
            uow.reserve_write()
            uow.tasks.add(Task(
                id="first", project_id=project_id, display_order=1, title="First",
                user_prompt="Original", user_prompt_history=[{
                    "id": "history", "prompt": "Earlier", "createdAt": "2026-10-11",
                }],
            ))
            uow.tasks.add(Task(
                id="second", project_id=project_id, display_order=2, title="Second",
            ))
            uow.jobs.add(Job(
                id="job", project_id=project_id, task_id="first",
                status=JobStatus.COMPLETED, final_prompt_snapshot="Frozen",
                task_content_snapshot={"title": "First"}, assets_snapshot=[],
                generation_profile_snapshot={}, provider_profile_snapshot={"model": "local"},
                params_snapshot={"seed": 8}, context_snapshot={},
                provider_job_id="remote-42",
            ))
            uow.results.add(Result(
                id="result", project_id=project_id, task_id="first", job_id="job",
                video_url=f"/media/{project_id}/outputs/job/clip.mp4",
            ))
            uow.prompt_revisions.add(AiPromptRevision(
                id="revision", project_id=project_id, task_id="first",
                source_user_prompt="Original", output_prompt="Enhanced", asset_ids=[],
                project_background_used=False, previous_task_summary_used=False,
                target_skill="h3", skill_version="1",
            ))
            uow.contexts.replace_for_target("second", [ContextLink(
                id="link", project_id=project_id, source_task_id="first",
                target_task_id="second", kind="visual", source_result_id="result",
            )])
        arranged = client.patch(f"/api/v1/projects/{project_id}/tasks/first/timeline", json={
            "startSeconds": 1.5, "durationSeconds": 7.25,
        })
        assert arranged.status_code == 200, arranged.text
        assert arranged.json()["timelineStartSeconds"] == 1.5
        assert arranged.json()["durationSeconds"] == 7.25
        assert client.get(f"/api/v1/projects/{project_id}/workspace").json()["tasks"][1]["timelineStartSeconds"] is None
        director = {"globalPrompt": "清晨柔光", "globalPromptMode": "user"}
        patched = client.patch(f"/api/v1/projects/{project_id}", json={"director": director})
        assert patched.status_code == 200, patched.text
        with container.generation_service.uow_factory() as uow:
            uow.reserve_write()
            task = uow.tasks.get("first")
            task.generation_params = {**task.generation_params, "director": {"useGlobalPrompt": True}}
            uow.tasks.update(task)
        assert client.get(f"/api/v1/projects/{project_id}/settings").json()["director"] == director
        assert client.get(f"/api/v1/projects/{project_id}/tasks/first/editor").json()["generation"]["director"] == {"useGlobalPrompt": True}
        container.application_settings.update_local_inference(
            container.application_settings.get_local_inference(),
        )
    assert project_file.is_file()
    assert not (data / "unused.db").exists()
    assert (data / "application-settings.json").is_file()
    assert "local_inference" not in project_file.read_text(encoding="utf-8")
    (data / "recent-projects.json").unlink()

    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as reopened:
        response = reopened.post("/api/v1/projects/open", json={"path": str(project_file)})
        assert response.status_code == 200, response.text
        assert response.json()["id"] == project_id
        container = reopened.app.state.container
        with container.generation_service.uow_factory() as uow:
            assert uow.projects.get(project_id).title == "Film"
            assert uow.projects.get(project_id).director == director
            assert uow.tasks.get("first").user_prompt_history[0]["prompt"] == "Earlier"
            assert uow.tasks.get("first").timeline_start_seconds == 1.5
            assert uow.tasks.get("first").planned_duration_seconds == 7.25
            assert uow.tasks.get("first").generation_params["director"] == {"useGlobalPrompt": True}
            assert [task.id for task in uow.tasks.list_by_project(project_id)] == ["first", "second"]
            assert uow.jobs.get("job").provider_job_id == "remote-42"
            assert uow.jobs.get("job").params_snapshot == {"seed": 8}
            assert uow.results.get("result").task_id == "first"
            assert uow.prompt_revisions.get("revision").output_prompt == "Enhanced"
            assert uow.contexts.list_by_target("second")[0].source_result_id == "result"
        assert reopened.get(f"/api/v1/projects/{project_id}/workspace").status_code == 200
        assert reopened.patch(f"/api/v1/projects/{project_id}", json={
            "title": "Reopened film",
        }).status_code == 200
    assert "Reopened film" in project_file.read_text(encoding="utf-8")


def test_failed_document_save_keeps_original_and_rolls_back_edit(tmp_path, providers,
                                                                 monkeypatch):
    from shotmill.persistence import project_documents

    data = tmp_path / "app"
    path = tmp_path / "film.shotmill"
    settings = Settings(
        app_name="ShotMill", api_version="0.3", data_root=data,
        database_url=f"sqlite+pysqlite:///{(data / 'unused.db').as_posix()}",
    )
    with TestClient(create_app(settings, prompt_provider=providers[0],
                               video_provider=providers[1])) as client:
        created = client.post("/api/v1/projects", json={
            "title": "Original", "path": str(path),
        }).json()
        original = path.read_bytes()
        write = project_documents._atomic_json

        def fail(target, value):
            if target == path:
                raise OSError("disk full")
            return write(target, value)

        monkeypatch.setattr(project_documents, "_atomic_json", fail)
        with pytest.raises(OSError, match="disk full"):
            client.patch(f"/api/v1/projects/{created['id']}", json={"title": "Unsaved"})
        assert path.read_bytes() == original
        with client.app.state.container.generation_service.uow_factory() as uow:
            assert uow.projects.get(created["id"]).title == "Original"
        monkeypatch.setattr(project_documents, "_atomic_json", write)
        assert client.patch(f"/api/v1/projects/{created['id']}", json={
            "title": "Saved",
        }).status_code == 200
        assert b"Saved" in path.read_bytes()
