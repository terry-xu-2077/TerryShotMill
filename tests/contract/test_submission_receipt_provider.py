import asyncio

import httpx
import pytest
from shotmill.domain.providers import VideoGenerationRequest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


@pytest.mark.parametrize("receipt", ["lost", "server-error", "invalid-json", "missing-id"])
@pytest.mark.parametrize("observation", ["missing", "server-error", "invalid-json"])
def test_uncertain_submission_observes_original_job_without_resubmitting(
    monkeypatch, receipt, observation
):
    calls, progress = [], []
    queries = 0

    async def handler(request):
        nonlocal queries
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            assert progress[-1]["submissionState"] == "sending"
            if receipt == "lost":
                raise httpx.ReadTimeout("receipt lost", request=request)
            if receipt == "server-error":
                return httpx.Response(502)
            if receipt == "invalid-json":
                return httpx.Response(200, content=b"broken response")
            return httpx.Response(200, json={"ok": True})
        if "/files/" in request.url.path:
            return httpx.Response(200, content=b"original result")
        queries += 1
        if queries == 1:
            if observation == "server-error":
                return httpx.Response(500)
            if observation == "invalid-json":
                return httpx.Response(200, content=b"broken observation")
            return httpx.Response(404, json={"status": "not_found"})
        return httpx.Response(200, json={
            "status": "completed", "promptId": "original-remote",
            "results": [{"filename": "clip.mp4"}],
        })

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.001,
    )
    provider.frozen_workflow_id = "workflow.json"
    provider.workflow_snapshot = {"prompt": {}}

    async def validated(*args, **kwargs):
        return []

    async def uploaded(*args, **kwargs):
        return {}

    async def report(update):
        progress.append(update)

    monkeypatch.setattr(provider, "_validate_workflow_inputs", validated)
    monkeypatch.setattr(provider, "_upload_assets", uploaded)
    provider.set_progress_callback(report)
    request = VideoGenerationRequest("logical-job", "p", "t", "prompt", (), {})
    result = asyncio.run(provider.generate(request))
    try:
        assert result.provider_job_id == "original-remote"
        assert result.outputs[0].content.read() == b"original result"
        assert [method for method, _ in calls].count("POST") == 1
        assert queries == 2
        assert any(item.get("submissionState") == "uncertain" for item in progress)
        assert any(item.get("submissionState") == "accepted" for item in progress)
    finally:
        result.close()


def test_restarted_uncertain_submission_waits_for_original_receipt_without_post():
    queries = 0

    def handler(request):
        nonlocal queries
        assert request.method == "GET"
        if "/files/" in request.url.path:
            return httpx.Response(200, content=b"original")
        queries += 1
        if queries == 1:
            return httpx.Response(404)
        return httpx.Response(200, json={
            "status": "completed", "promptId": "original",
            "results": [{"filename": "clip.mp4"}],
        })

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.001,
    )
    provider.set_recovery_context({"submissionState": "sending"})
    response = asyncio.run(provider.resume("logical-job"))
    response.close()
    assert queries == 2


def test_stop_unknown_submission_uses_durable_fence_without_queue_interrupt():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"status": "cancelled", "jobId": "job"})

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
    )
    asyncio.run(provider.stop("job"))
    assert calls == [("POST", "/shotmill/v1/jobs/job/cancel-submission")]


@pytest.mark.parametrize("uncertain", [False, True])
def test_cancelled_receipt_is_terminal_even_without_prompt_id(uncertain):
    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "cancelled", "jobId": "job"})
        ),
    )
    if uncertain:
        provider.set_recovery_context({"submissionState": "uncertain"})

    async def run():
        return await asyncio.wait_for(provider.resume("job"), timeout=0.5)

    with pytest.raises(ShotMillError) as error:
        asyncio.run(run())
    assert error.value.code == "GENERATION_CANCELLED"


def test_late_submission_rejected_by_fence_reports_cancellation():
    provider = ComfyUIVideoGenerationProvider("http://desktop", None)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(409, json={"error": "submission_cancelled"})
        )) as client:
            await provider._submit_once(client, "http://desktop/jobs", {"jobId": "job"})

    with pytest.raises(ShotMillError) as error:
        asyncio.run(run())
    assert error.value.code == "GENERATION_CANCELLED"


def test_restart_retries_persisted_stop_intent_after_transient_disconnect():
    calls = []
    attempts = 0

    def handler(request):
        nonlocal attempts
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(200, json={"status": "cancelled"})
        return httpx.Response(
            200 if attempts > 1 else 404,
            json={"status": "cancelled" if attempts > 1 else "not_found"},
        )

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.001,
    )
    provider.set_recovery_context({"submissionState": "uncertain", "stopRequested": True})

    async def run():
        await asyncio.wait_for(provider.resume("job"), timeout=3)

    with pytest.raises(ShotMillError) as error:
        asyncio.run(run())
    assert error.value.code == "GENERATION_CANCELLED"
    assert attempts == 2
    assert all(path.endswith("cancel-submission") for method, path in calls if method == "POST")


def test_recovered_stop_failure_does_not_discard_completed_result():
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(500)
        if "/files/" in request.url.path:
            return httpx.Response(200, content=b"finished before stop")
        return httpx.Response(200, json={
            "status": "completed", "promptId": "original",
            "results": [{"filename": "clip.mp4"}],
        })

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
    )
    provider.set_recovery_context({"stopRequested": True, "submissionState": "uncertain"})
    response = asyncio.run(provider.resume("job"))
    try:
        assert response.outputs[0].content.read() == b"finished before stop"
        assert response.provider_job_id == "original"
        assert sum(request.method == "POST" for request in calls) == 1
    finally:
        response.close()


def test_unconfirmed_stop_and_missing_receipt_remain_pending_until_shutdown():
    async def run():
        queried = asyncio.Event()

        def handler(request):
            if request.method == "POST":
                return httpx.Response(409, json={"error": "submission_state_unknown"})
            queried.set()
            return httpx.Response(404)

        provider = ComfyUIVideoGenerationProvider(
            "http://desktop", None, transport=httpx.MockTransport(handler),
        )
        provider.set_recovery_context({"stopRequested": True, "submissionState": "accepted"})
        work = asyncio.create_task(provider.resume("job"))
        try:
            await asyncio.wait_for(queried.wait(), timeout=3)
            assert not work.done()
        finally:
            work.cancel()
            with pytest.raises(asyncio.CancelledError):
                await work

    asyncio.run(run())


def test_recovered_uncertain_queued_stop_resolves_submission_identity():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("cancel-submission"):
            return httpx.Response(200, json={"status": "queued", "promptId": "original"})
        if request.method == "POST":
            return httpx.Response(200)
        return httpx.Response(404)

    provider = ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
    )
    provider.set_recovery_context({"stopRequested": True, "submissionState": "uncertain"})

    async def run():
        await asyncio.wait_for(provider.resume("job"), timeout=3)

    with pytest.raises(ShotMillError) as error:
        asyncio.run(run())
    assert error.value.code == "SHOTMILL_BRIDGE_JOB_NOT_FOUND"
    assert [request.url.path for request in calls] == [
        "/shotmill/v1/jobs/job/cancel-submission", "/queue", "/interrupt",
        "/shotmill/v1/jobs/job",
    ]
