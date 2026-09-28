import asyncio
import hashlib

import httpx
import pytest
from shotmill.domain.providers import PromptAIRequest, ResolvedMedia, VideoGenerationRequest
from shotmill.providers.prompt_ai.comfyui import ComfyUIPromptAIProvider
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


@pytest.mark.parametrize("kind", ["prompt", "video"])
@pytest.mark.parametrize("logical_name", ["portrait.PNG", None])
def test_provider_upload_uses_logical_extension_for_content_addressed_media(
    tmp_path, kind, logical_name,
):
    content = b"image-bytes"
    checksum = hashlib.sha256(content).hexdigest()
    path = tmp_path / (checksum if logical_name else "legacy.png")
    path.write_bytes(content)
    media = ResolvedMedia(
        "asset-a", "<Picture 1>", None, "image", path, "image/png",
        original_filename=logical_name,
    )
    uploads = []

    async def handler(request):
        body = await request.aread()
        assert b'filename="asset-a.png"' in body
        assert b"Content-Type: image/png" in body
        assert content in body
        uploads.append(body)
        return httpx.Response(200, json={
            "asset": {"relativePath": "shotmill/a.png", "sha256": checksum},
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            if kind == "prompt":
                provider = ComfyUIPromptAIProvider("http://bridge")
                request = PromptAIRequest("system", "prompt", (media,))
            else:
                provider = ComfyUIVideoGenerationProvider("http://bridge", None)
                request = VideoGenerationRequest("j", "p", "t", "prompt", (media,), {})
            await provider._upload_assets(client, request, "http://bridge")

    asyncio.run(run())
    assert len(uploads) == 1
