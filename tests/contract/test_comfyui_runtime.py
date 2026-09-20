from __future__ import annotations

import asyncio

import httpx
from shotmill.providers.comfyui_runtime import ComfyUIExecutionCoordinator


def test_comfyui_memory_release_only_happens_on_workload_switch() -> None:
    asyncio.run(_run_test())


async def _run_test() -> None:
    free_calls: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/shotmill/v1/runtime/prepare":
            free_calls.append({"route": request.url.path})
            return httpx.Response(200)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    coordinator = ComfyUIExecutionCoordinator()
    async with httpx.AsyncClient(
        base_url="http://comfyui.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        await coordinator.prepare("prompt", client, "http://comfyui.test")
        await coordinator.finish()
        await coordinator.prepare("prompt", client, "http://comfyui.test")
        await coordinator.finish()
        await coordinator.prepare("video", client, "http://comfyui.test")
        await coordinator.finish()
        await coordinator.prepare("video", client, "http://comfyui.test")
        await coordinator.finish()

    assert free_calls == [{"route": "/shotmill/v1/runtime/prepare"}]
