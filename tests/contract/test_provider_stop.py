import asyncio
import json

import httpx
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
    assert calls[0].url.path == "/shotmill/v1/jobs/logical-job"
    assert calls[1].url.path == "/queue"
    assert json.loads(calls[1].content) == {"delete": ["exact-remote"]}
    assert calls[2].url.path == "/interrupt"
    assert json.loads(calls[2].content) == {"prompt_id": "exact-remote"}
