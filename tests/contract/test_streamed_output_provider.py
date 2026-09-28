import asyncio
import hashlib

import httpx
import pytest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation import comfyui


@pytest.mark.parametrize("mode", ["success", "retry", "checksum", "cancel", "callback"])
def test_streamed_download_ownership_retry_and_failure_cleanup(monkeypatch, mode):
    block = b"v" * (1024 * 1024)
    expected = hashlib.sha256(block * 16).hexdigest()
    opened = []
    temporary_file = comfyui.tempfile.TemporaryFile

    def track_file(*args, **kwargs):
        stream = temporary_file(*args, **kwargs)
        opened.append(stream)
        return stream

    monkeypatch.setattr(comfyui.tempfile, "TemporaryFile", track_file)
    attempts = 0

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for index in range(16):
                yield block
                if index == 0:
                    if mode == "retry" and attempts == 1:
                        raise httpx.ReadError("mid-file disconnect")
                    if mode == "cancel":
                        raise asyncio.CancelledError()

    class StreamingOnlyResponse(httpx.Response):
        async def aread(self):
            raise AssertionError("Download must not buffer the complete response")

    def handler(request):
        nonlocal attempts
        assert request.method == "GET"
        if "/files/" not in request.url.path:
            return httpx.Response(200, json={
                "status": "completed", "promptId": "original",
                "results": [{"filename": "clip.mp4"}],
            })
        attempts += 1
        return StreamingOnlyResponse(200, stream=Body(), headers={
            "x-content-sha256": "0" * 64 if mode == "checksum" else expected,
        })

    provider = comfyui.ComfyUIVideoGenerationProvider(
        "http://desktop", None, transport=httpx.MockTransport(handler),
        poll_interval_seconds=0.001,
    )

    async def progress(update):
        if mode == "callback" and update.get("collectionState") == "downloaded":
            raise RuntimeError("progress persistence failed")

    provider.set_progress_callback(progress)
    if mode in {"success", "retry"}:
        result = asyncio.run(provider.resume("job"))
        try:
            stream = result.outputs[0].content
            assert not isinstance(stream, bytes)
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected
            assert stream.tell() == 16 * len(block)
            assert attempts == (2 if mode == "retry" else 1)
        finally:
            result.close()
    else:
        error = {"checksum": ShotMillError, "cancel": asyncio.CancelledError,
                 "callback": RuntimeError}[mode]
        with pytest.raises(error):
            asyncio.run(provider.resume("job"))
    assert opened and all(stream.closed for stream in opened)
