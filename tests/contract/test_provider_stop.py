import asyncio
import json

import httpx
import pytest
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


def test_stop_only_targets_requested_remote_prompt():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"status": "running", "promptId": "exact-remote"})

    provider = ComfyUIVideoGenerationProvider(
        "http://comfy", None, transport=httpx.MockTransport(handle)
    )
    asyncio.run(provider.stop("logical-job"))
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/shotmill/v1/jobs/logical-job/cancel-submission"
    assert calls[1].url.path == "/queue"
    assert json.loads(calls[1].content) == {"delete": ["exact-remote"]}
    assert calls[2].url.path == "/interrupt"
    assert json.loads(calls[2].content) == {"prompt_id": "exact-remote"}


@pytest.mark.parametrize("code", [409, 500])
def test_fence_failure_does_not_fall_back_to_unconfirmed_interrupt(code):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(code, json={"error": "submission_state_unknown"})

    provider = ComfyUIVideoGenerationProvider(
        "http://comfy", None, transport=httpx.MockTransport(handle),
    )
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(provider.stop("job"))
    assert len(calls) == 1


@pytest.mark.parametrize("known", [False, True])
def test_legacy_bridge_stop_requires_known_remote_identity(known):
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path.endswith("cancel-submission"):
            return httpx.Response(404)
        if request.method == "GET":
            return httpx.Response(
                200 if known else 404,
                json={"status": "running", "promptId": "original"} if known else {},
            )
        return httpx.Response(200)

    provider = ComfyUIVideoGenerationProvider(
        "http://comfy", None, transport=httpx.MockTransport(handle),
    )
    if known:
        asyncio.run(provider.stop("job"))
        assert json.loads(calls[2].content) == {"delete": ["original"]}
        assert json.loads(calls[3].content) == {"prompt_id": "original"}
    else:
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(provider.stop("job"))
        assert len(calls) == 2
