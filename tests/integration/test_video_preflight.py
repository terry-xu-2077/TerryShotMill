import json
from pathlib import Path

import httpx
import pytest
from shotmill.domain.application_settings import WorkflowNumericBinding
from shotmill.domain.entities import TaskAssetBinding
from shotmill.domain.enums import TaskState
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


def setup_task(client):
    project = client.post("/api/v1/projects", json={"title": "生成前检查"}).json()
    route = f"/api/v1/projects/{project['id']}"
    task = client.post(f"{route}/tasks", json={
        "title": "测试任务", "userPrompt": "雨夜码头", "promptSource": "user",
        "durationSeconds": 6, "generation": {}, "assetBindings": [],
    })
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    assert client.post(f"{route}/tasks/{task_id}/prompt-review").status_code == 200
    return project["id"], task_id, route


@pytest.mark.parametrize("catalog,code", [
    ([], "SHOTMILL_WORKFLOW_NOT_REGISTERED"),
    ([{"id": "w.json", "executable": False, "inputs": []}], "SHOTMILL_WORKFLOW_NOT_EXECUTABLE"),
])
def test_provider_preflight_rejects_before_queue_or_upload(client, catalog, code):
    project_id, task_id, route = setup_task(client)
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        assert request.method == "GET"
        assert request.url.path == "/shotmill/v1/workflows"
        return httpx.Response(200, json={"workflows": catalog})

    service = client.app.state.container.generation_service
    service.provider = ComfyUIVideoGenerationProvider(
        "http://bridge.test", Path("w.json"), transport=httpx.MockTransport(handler)
    )
    eligibility = client.post(f"{route}/video-generation-batches/eligibility",
                              json={"taskIds": [task_id]}).json()
    assert eligibility["eligibleTaskIds"] == []
    assert eligibility["skipped"][0]["code"] == code
    response = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert len(requests) == 2
    with service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task_id) == []


def test_task_changes_during_provider_validation_do_not_submit_stale_job(client, providers):
    project_id, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service

    async def validate(_request):
        with service.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            task.revision += 1
            task.user_prompt = task.final_prompt = "已修改的提示词"
            uow.tasks.update(task)

    providers[1].validate = validate
    response = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "TASK_REVISION_CONFLICT"
    with service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task_id) == []


def test_active_video_job_blocks_duplicate_even_if_task_display_state_changed(client):
    _, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service

    class HeldQueue:
        async def enqueue(self, _job_id):
            pass

    service.attach_queue(HeldQueue())
    first = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert first.status_code == 202, first.text
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.state = TaskState.PROMPT_GENERATING
        uow.tasks.update(task)
    duplicate = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "TASK_BUSY"


def test_batch_submission_allows_review_invalidation_after_provider_validation(client, providers):
    project_id, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service
    calls = 0

    async def validate(_request):
        nonlocal calls
        calls += 1
        if calls == 2:
            with service.uow_factory() as uow:
                task = uow.tasks.get(task_id)
                task.approved_prompt_hash = None
                uow.tasks.update(task)

    providers[1].validate = validate
    result = client.post(f"{route}/video-generation-batches", json={"taskIds": [task_id]})
    assert result.status_code == 202, result.text
    assert result.json()["eligibleTaskIds"] == [task_id]
    assert result.json()["skipped"] == []
    with service.uow_factory() as uow:
        assert len(uow.jobs.list_by_task(task_id)) == 1


@pytest.mark.parametrize("missing_file", [False, True])
def test_media_mismatch_and_missing_files_are_rejected_in_preflight(client, missing_file):
    project_id, task_id, route = setup_task(client)
    upload = client.post(f"{route}/assets", files={
        "file": ("test.png", b"image-bytes", "image/png"),
    }, data={"name": "参考图", "category": "character", "tags": "[]"})
    assert upload.status_code == 201, upload.text
    asset_id = upload.json()["id"]
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.asset_bindings = [TaskAssetBinding(asset_id, "<Picture 1>")]
        uow.tasks.update(task)
        asset = uow.assets.get(asset_id)
        path = service.storage.resolve(project_id, asset.project_relative_path)
    if missing_file:
        path.unlink()
    requests = []

    def handler(request):
        requests.append(request.method)
        assert request.method == "GET"
        return httpx.Response(200, json={"workflows": [{
            "id": "w.json", "inputs": [{"type": "VIDEO"}], "executable": True,
        }]})

    service.provider = ComfyUIVideoGenerationProvider(
        "http://bridge.test", Path("w.json"), transport=httpx.MockTransport(handler)
    )
    result = client.post(f"{route}/video-generation-batches/eligibility",
                         json={"taskIds": [task_id]}).json()
    assert result["eligibleTaskIds"] == []
    expected = (
        "GENERATION_ASSET_FILE_MISSING" if missing_file
        else "SHOTMILL_WORKFLOW_INPUT_TYPE_MISMATCH"
    )
    assert result["skipped"][0]["code"] == expected
    assert requests == ([] if missing_file else ["GET"])
    with service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task_id) == []


def test_preflight_checks_capability_duration_without_starting_generation(client, providers):
    _, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service
    with service.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        task.planned_duration_seconds = 16
        uow.tasks.update(task)
    result = client.post(f"{route}/video-generation-batches/eligibility",
                         json={"taskIds": [task_id]}).json()
    assert result["eligibleTaskIds"] == []
    assert result["skipped"][0]["code"] == "GENERATION_DURATION_UNSUPPORTED"
    assert "15 秒" in result["skipped"][0]["message"]
    assert providers[1].requests == []


def test_queued_video_keeps_validated_endpoint_and_workflow_after_settings_change(
    client, bridge_snapshot,
):
    _, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service
    current = {"url": "http://original.test", "workflow": Path("workflows/group/w.json")}
    bindings = [
        WorkflowNumericBinding("7:frames:2", "frameCount", frame_multiple=4, frame_offset=1)
    ]
    submitted = []
    ports = [{
        "type": "INT", "targetNodeId": "7", "targetPort": "frames", "sourceNodeId": "2",
    }]
    original = bridge_snapshot("group/w.json", ports)
    reads = []

    def handler(request):
        assert request.url.host == "original.test"
        if request.url.path.endswith("/workflows/validate"):
            assert current["workflow"] == Path("workflows/group/w.json")
            assert json.loads(request.content)["numericInputs"] == {"7:frames:2": 145}
            return httpx.Response(200, json={"ok": True})
        if request.url.path.endswith("/workflows/snapshot"):
            reads.append("snapshot")
            assert current["workflow"] == Path("workflows/group/w.json")
            return httpx.Response(200, json={"snapshot": original})
        if request.url.path.endswith("/workflows"):
            assert current["workflow"] == Path("workflows/group/w.json")
            return httpx.Response(200, json={"workflows": [{
                "id": "group/w.json", "inputs": ports, "executable": True,
            }]})
        if request.method == "POST":
            submitted.append(json.loads(request.content))
            return httpx.Response(200, json={"promptId": "remote-job"})
        if "/files/" in request.url.path:
            return httpx.Response(200, content=b"result", headers={"content-type": "image/png"})
        return httpx.Response(200, json={
            "status": "completed", "results": [{"filename": "result.png"}],
        })

    class HeldQueue:
        async def enqueue(self, _job_id):
            pass

    service.attach_queue(HeldQueue())
    service.provider = ComfyUIVideoGenerationProvider(
        None, None, base_url_getter=lambda: current["url"],
        workflow_path_getter=lambda _: current["workflow"], transport=httpx.MockTransport(handler),
        numeric_bindings_getter=lambda _: bindings,
    )
    response = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    with service.uow_factory() as uow:
        assert uow.jobs.get(job_id).provider_profile_snapshot["workflowSnapshot"] == original
    current.update(url="http://changed.test", workflow=Path("workflows/other.json"))
    bindings.clear()
    # Rebuild the adapter too: configuration must come from the persisted Job.
    service.provider = ComfyUIVideoGenerationProvider(
        current["url"], current["workflow"], transport=httpx.MockTransport(handler)
    )
    client.portal.call(service.execute, job_id)
    assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "completed"
    assert submitted[0]["workflowId"] == "group/w.json"
    assert submitted[0]["numericInputs"] == {"7:frames:2": 145}
    assert submitted[0]["inputSlots"] == []
    assert submitted[0]["workflowSnapshot"] == original
    assert reads == ["snapshot"]


@pytest.mark.parametrize(
    "failure", ["unsupported", "compile", "corrupt", "ports_changed", "malformed_response"],
)
def test_workflow_capture_failure_never_queues_or_uploads(client, bridge_snapshot, failure):
    _, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service
    ports = [{"type": "INT", "targetNodeId": "7", "targetPort": "frames", "sourceNodeId": "2"}]
    snapshot = bridge_snapshot(inputs=ports)
    if failure == "corrupt":
        snapshot["prompt"]["1"]["inputs"]["value"] = 99
    if failure == "ports_changed":
        snapshot = bridge_snapshot(inputs=[])
    requests = []

    def handler(request):
        requests.append(request.url.path)
        assert request.method == "GET", "preflight must not upload or submit"
        if request.url.path.endswith("/workflows"):
            return httpx.Response(200, json={"workflows": [{"id": "w.json", "inputs": ports}]})
        assert request.url.path.endswith("/workflows/snapshot")
        if failure == "unsupported":
            return httpx.Response(404, json={"error": "not found"})
        if failure == "compile":
            return httpx.Response(400, json={"error": "Broken subgraph 42"})
        if failure == "malformed_response":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"snapshot": snapshot})

    service.provider = ComfyUIVideoGenerationProvider(
        "http://bridge.test", Path("w.json"), transport=httpx.MockTransport(handler),
        numeric_bindings_getter=lambda _: [WorkflowNumericBinding("7:frames:2", "frameCount")],
    )
    response = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert response.status_code == (502 if failure == "malformed_response" else 422), response.text
    expected = {
        "unsupported": "WORKFLOW_SNAPSHOT_UNAVAILABLE",
        "compile": "WORKFLOW_COMPILE_FAILED",
        "corrupt": "WORKFLOW_SNAPSHOT_INVALID",
        "ports_changed": "WORKFLOW_NUMERIC_BINDING_STALE",
        "malformed_response": "SHOTMILL_BRIDGE_INVALID_RESPONSE",
    }
    assert response.json()["error"]["code"] == expected[failure]
    if failure == "compile":
        assert "42" in response.text
    assert requests == ["/shotmill/v1/workflows", "/shotmill/v1/workflows/snapshot"]
    with service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task_id) == []


def test_native_preflight_rejects_missing_model_before_job_creation(client, bridge_snapshot):
    _, task_id, route = setup_task(client)
    service = client.app.state.container.generation_service
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/workflows"):
            return httpx.Response(200, json={"workflows": [{"id": "w.json", "inputs": []}]})
        if request.url.path.endswith("/workflows/snapshot"):
            return httpx.Response(200, json={"snapshot": bridge_snapshot()})
        assert request.url.path == "/shotmill/v1/workflows/validate"
        body = json.loads(request.content)
        assert body["workflowSnapshot"]["workflowId"] == "w.json"
        assert body["finalPrompt"] == "雨夜码头"
        assert "assetValues" not in body
        return httpx.Response(400, json={
            "ok": False, "error": "Prompt validation failed",
            "nodeErrors": {"42": {"errors": [{
                "type": "value_not_in_list",
                "message": "Model missing", "details": "model.safetensors",
            }]}},
        })

    service.provider = ComfyUIVideoGenerationProvider(
        "http://bridge.test", Path("w.json"), transport=httpx.MockTransport(handler),
    )
    response = client.post(f"{route}/tasks/{task_id}/generation", json={})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_PREFLIGHT_FAILED"
    assert "42" in response.text and "model.safetensors" in response.text
    assert "所选模型或选项不可用" in response.text
    assert "nodeErrors" not in response.text
    assert calls[-1] == "/shotmill/v1/workflows/validate"
    with service.uow_factory() as uow:
        assert uow.jobs.list_by_task(task_id) == []
