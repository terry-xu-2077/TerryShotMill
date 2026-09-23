import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from shotmill.domain.entities import ContextLink, new_id
from shotmill.domain.providers import GeneratedOutput, VideoGenerationResponse
from shotmill.errors import ShotMillError

from tests.integration.test_assets_prompt_generation import _wait_job


def setup_context(client, providers, mode):
    video = providers[1]

    async def generate(request):
        video.requests.append(request)
        return VideoGenerationResponse(
            "fixture",
            (
                GeneratedOutput(
                    "source.mp4",
                    Path("backend/shotmill/devtools/fixtures/preview.mp4").read_bytes(),
                    "video/mp4",
                ),
            ),
        )

    video.generate = generate
    project = client.post("/api/v1/projects", json={"title": "Context media"}).json()
    route = f"/api/v1/projects/{project['id']}/tasks"
    source = client.post(
        route, json={"title": "Source", "userPrompt": "Source", "durationSeconds": 2}
    ).json()
    job = client.post(f"{route}/{source['id']}/generation", json={}).json()
    assert _wait_job(client, job["id"])["status"] == "completed"
    target = client.post(
        route,
        json={
            "title": "Target",
            "userPrompt": "Continue",
            "generation": {"contextMode": mode, "contextStartSeconds": 1, "contextEndSeconds": 2},
        },
    ).json()
    return project["id"], source["id"], target["id"], route


@pytest.mark.parametrize("mode,media_type", [("尾帧承接", "image"), ("片段承接", "video")])
def test_context_is_real_media_and_frozen_before_queue(client, providers, mode, media_type):
    project, source, target, route = setup_context(client, providers, mode)
    service = client.app.state.container.generation_service

    class HeldQueue:
        async def enqueue(self, _job_id):
            pass

    service.attach_queue(HeldQueue())
    response = client.post(f"{route}/{target}/generation", json={})
    assert response.status_code == 202, response.text
    job = service.get_job(response.json()["id"])
    request = service._provider_request(job)
    assert len(request.assets) == 1
    media = request.assets[0]
    assert media.media_type == media_type
    digest = hashlib.sha256(media.path.read_bytes()).hexdigest()
    snapshot = job.context_snapshot["media"][0]
    assert snapshot["sha256"] == digest
    assert snapshot["sourceTaskId"] == source
    assert snapshot["sourceResultId"] == job.context_snapshot["links"][0]["sourceResultId"]
    if media_type == "video":
        from shotmill.media.context import video_duration

        assert video_duration(media.path) == pytest.approx(1, abs=0.05)
    with service.uow_factory() as uow:
        upstream = uow.tasks.get(source)
        upstream.primary_result_id = None
        uow.tasks.update(upstream)
        uow.contexts.mark_stale_by_source(source)
    assert service._provider_request(job).assets[0].path.read_bytes() == media.path.read_bytes()
    assert hashlib.sha256(media.path.read_bytes()).hexdigest() == digest
    media.path.write_bytes(b"changed")
    with pytest.raises(ShotMillError, match="上下文媒体"):
        service._provider_request(job)


def test_actual_video_duration_overrides_plan_in_editor_and_saved_range(client, providers):
    project, source, target, route = setup_context(client, providers, "不承接")
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        task = uow.tasks.get(source)
        task.planned_duration_seconds = 15
        uow.tasks.update(task)
    editor = client.get(f"{route}/{target}/editor").json()
    assert editor["previousTaskDurationSeconds"] == pytest.approx(2)
    response = client.patch(
        f"{route}/{target}",
        json={
            "title": "Target",
            "userPrompt": "Continue",
            "generation": {"contextMode": "片段承接"},
        },
    )
    assert response.status_code == 200, response.text
    saved = client.get(f"{route}/{target}/editor").json()["generation"]
    assert saved["contextStartSeconds"] == pytest.approx(1)
    assert saved["contextEndSeconds"] == pytest.approx(2)


@pytest.mark.parametrize("old_metadata", [{}, {"durationSeconds": 15}])
def test_old_primary_result_gets_measured_duration_without_rewriting_history(
    client, providers, old_metadata
):
    project, source, _, _ = setup_context(client, providers, "不承接")
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        task = uow.tasks.get(source)
        original = uow.results.get(task.primary_result_id)
        legacy = replace(original, id=new_id("result"), metadata=old_metadata)
        assert legacy.preview_url
        uow.results.add(legacy)
        task.primary_result_id = legacy.id
        task.planned_duration_seconds = 6
        uow.tasks.update(task)
    workspace = client.get(f"/api/v1/projects/{project}/workspace").json()
    summary = next(item for item in workspace["tasks"] if item["id"] == source)
    assert summary["durationSeconds"] == 6
    assert summary["primaryResult"]["durationSeconds"] == pytest.approx(2)
    with service.uow_factory() as uow:
        assert uow.results.get(legacy.id).metadata == old_metadata


def test_stale_source_refreshes_automatically_but_no_context_is_isolated(client, providers):
    _, source, target, route = setup_context(client, providers, "尾帧承接")
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        upstream = uow.tasks.get(source)
        old_id = upstream.primary_result_id
        latest = replace(uow.results.get(old_id), id=new_id("result"))
        uow.results.add(latest)
        upstream.primary_result_id = latest.id
        uow.tasks.update(upstream)
        uow.contexts.mark_stale_by_source(source)
    response = client.post(f"{route}/{target}/generation", json={})
    assert response.status_code == 202, response.text
    assert _wait_job(client, response.json()["id"])["status"] == "completed"
    job = service.get_job(response.json()["id"])
    assert job.context_snapshot["links"][0]["sourceResultId"] == latest.id
    assert job.context_snapshot["media"][0]["sourceResultId"] == latest.id
    response = client.patch(
        f"{route}/{target}",
        json={
            "title": "Target",
            "userPrompt": "Independent",
            "generation": {"contextMode": "不承接"},
        },
    )
    assert response.status_code == 200, response.text
    job = client.post(f"{route}/{target}/generation", json={}).json()
    assert _wait_job(client, job["id"])["status"] == "completed"
    assert providers[1].requests[-1].assets == ()
    assert service.get_job(job["id"]).context_snapshot == {"links": [], "media": []}


def test_cross_project_context_cannot_read_another_project_result(client, providers):
    _, source, _, _ = setup_context(client, providers, "不承接")
    project = client.post("/api/v1/projects", json={"title": "Other project"}).json()["id"]
    route = f"/api/v1/projects/{project}/tasks"
    target = client.post(
        route,
        json={
            "title": "Target",
            "userPrompt": "Continue",
            "generation": {"contextMode": "尾帧承接"},
        },
    ).json()["id"]
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        upstream = uow.tasks.get(source)
        uow.contexts.replace_for_target(
            target,
            [
                ContextLink(
                    "foreign-context", project, source, target, "visual", upstream.primary_result_id
                )
            ],
        )
    response = client.post(f"{route}/{target}/generation", json={})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONTEXT_RESULT_REQUIRED"


def test_missing_source_result_warns_before_submission_and_allows_generation(client):
    project = client.post("/api/v1/projects", json={"title": "Missing"}).json()["id"]
    route = f"/api/v1/projects/{project}/tasks"
    client.post(route, json={"title": "Source", "userPrompt": "Source"})
    target = client.post(
        route,
        json={
            "title": "Target",
            "userPrompt": "Continue",
            "generation": {"contextMode": "尾帧承接"},
        },
    ).json()["id"]
    preview = client.post(
        f"/api/v1/projects/{project}/video-generation-batches/eligibility",
        json={"taskIds": [target]},
    ).json()
    assert preview["eligibleTaskIds"] == [target]
    assert preview["warnings"][0]["taskId"] == target
    assert "不使用尾帧承接" in preview["warnings"][0]["message"]
    workspace = client.get(f"/api/v1/projects/{project}/workspace").json()
    assert workspace["tasks"][1]["generationWarnings"]
    response = client.post(f"{route}/{target}/generation", json={})
    assert response.status_code == 202, response.text
    service = client.app.state.container.generation_service
    job = service.get_job(response.json()["id"])
    assert job.params_snapshot["contextMode"] == "不承接"
    assert job.context_snapshot["warnings"]
    assert job.context_snapshot["media"] == []


def test_default_tail_continuation_and_first_task_generation(client):
    project = client.post("/api/v1/projects", json={"title": "Defaults"}).json()
    route = f"/api/v1/projects/{project['id']}"
    task = client.post(f"{route}/tasks", json={"title": "First", "userPrompt": "Scene"}).json()
    with client.app.state.container.generation_service.uow_factory() as uow:
        saved = uow.tasks.get(task["id"])
        assert saved.generation_params["contextMode"] == "尾帧承接"
        assert saved.user_view_mode == saved.ai_view_mode == "visual"
    preview = client.post(f"{route}/video-generation-batches/eligibility",
                          json={"taskIds": [task["id"]]}).json()
    assert preview["eligibleTaskIds"] == [task["id"]]
    assert preview["warnings"] == []
    summary = client.get("/api/v1/projects").json()["items"][0]
    assert summary["createdAt"] == project["createdAt"]


def test_segment_submission_resolves_previous_result_without_resaving(client, providers):
    _, source, target, route = setup_context(client, providers, "片段承接")
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        uow.contexts.replace_for_target(target, [])
    response = client.post(f"{route}/{target}/generation", json={})
    assert response.status_code == 202, response.text
    job = service.get_job(response.json()["id"])
    assert job.context_snapshot["links"][0]["sourceTaskId"] == source
    assert job.context_snapshot["media"][0]["mediaType"] == "video"
