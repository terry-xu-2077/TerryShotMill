from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from shotmill.domain.providers import PromptAIRequest, ResolvedMedia
from shotmill.providers.prompt_ai.comfyui import ComfyUIPromptAIProvider


def test_comfyui_prompt_provider_builds_builtin_graph_uploads_and_reads_output(
    tmp_path: Path,
) -> None:
    asyncio.run(_run_comfyui_prompt_provider_test(tmp_path))


async def _run_comfyui_prompt_provider_test(tmp_path: Path) -> None:
    asset_path = tmp_path / "character.png"
    asset_path.write_bytes(b"png")
    submitted: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/shotmill/v1/assets":
            return httpx.Response(
                200,
                json={"ok": True, "asset": {"relativePath": "shotmill/asset.png"}},
            )
        if request.url.path == "/shotmill/v1/jobs":
            submitted.update(json.loads(request.content))
            return httpx.Response(200, json={"promptId": "prompt-1"})
        if request.url.path.startswith("/shotmill/v1/jobs/"):
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "nodeOutputs": {
                        "1": {"string": ["analysis</think>rewritten H3 prompt"]}
                    },
                },
            )
        raise AssertionError(f"Unexpected ComfyUI request: {request.method} {request.url}")

    provider = ComfyUIPromptAIProvider(
        "http://comfyui.test",
        poll_interval_seconds=0.1,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    response = await provider.enhance(
        PromptAIRequest(
            system_prompt="ShotMill system rules",
            user_text="Describe this character for H3.",
            media=(
                ResolvedMedia(
                    asset_id="asset-a",
                    reference="<Picture 1>",
                    role="character",
                    media_type="image",
                    path=asset_path,
                    mime_type="image/png",
                ),
            ),
        )
    )

    assert response.text == "rewritten H3 prompt"
    assert response.provider_id == "comfyui-llama-cpp-vllm"
    prompt = submitted["prompt"]
    assert prompt["3"]["inputs"]["model"] == "Qwen3.8-27B-Q4_K_M.gguf"
    assert prompt["3"]["inputs"]["n_ctx"] == 16384
    assert prompt["1"]["inputs"]["max_frames"] == 24
    assert prompt["1"]["inputs"]["max_size"] == 256
    assert prompt["1"]["inputs"]["inference_mode"] == "images"
    assert prompt["1"]["inputs"]["custom_prompt"] == "Describe this character for H3."
    assert prompt["1"]["inputs"]["system_prompt"] == "ShotMill system rules"
    assert prompt["6"]["inputs"]["image"] == "shotmill/asset.png"
    assert prompt["1"]["inputs"]["images"] == ["12", 0]
    assert prompt["15"]["class_type"] == "TerryXuH3PromptEditor"
    assert prompt["15"]["inputs"]["source_text"] == ["1", 0]
    assert "13" not in prompt
    assert "14" not in prompt
