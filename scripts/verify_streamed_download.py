"""Local real-HTTP download/storage smoke; run with ComfyUI's Python (aiohttp).

Uses an ephemeral loopback server and temporary media, never live ComfyUI jobs.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import sys
import tempfile
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shotmill.media.storage import MediaStorage  # noqa: E402
from shotmill.providers.video_generation.comfyui import (  # noqa: E402
    ComfyUIVideoGenerationProvider,
)


async def main() -> None:
    source = ROOT / "integrations/comfyui_shotmill/bridge_api.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == "_result_file"]
    with tempfile.TemporaryDirectory(prefix="shotmill-download-smoke-") as directory:
        root = Path(directory)
        remote = root / "remote"
        remote.mkdir()
        digest = hashlib.sha256()
        block = b"video123" * (128 * 1024)
        size = 128 * len(block)
        with (remote / "clip.mp4").open("wb") as output:
            for _ in range(128):
                output.write(block)
                digest.update(block)
        state = {"status": "completed", "promptId": "existing-remote",
                 "results": [{"filename": "clip.mp4"}]}
        scope = {
            "web": web, "asyncio": asyncio, "hashlib": hashlib, "Path": Path,
            "JOB_INDEX": None, "_safe_name": lambda value, fallback: value,
            "_load_index": lambda _: {"jobs": {"job": {}}},
            "_job_state": lambda _: state,
            "folder_paths": SimpleNamespace(get_output_directory=lambda: str(remote)),
        }
        exec(compile(tree, str(source), "exec"), scope)

        async def status(request):
            return web.json_response(state)

        app = web.Application()
        app.router.add_get("/shotmill/v1/jobs/{job_id}", status)
        app.router.add_get(
            "/shotmill/v1/results/{job_id}/files/{index}", scope["_result_file"]
        )
        storage = MediaStorage(root / "local")
        async with TestServer(app, host="127.0.0.1") as server:
            provider = ComfyUIVideoGenerationProvider(str(server.make_url("")), None)
            tracemalloc.start()
            result = None
            try:
                result = await provider.resume("job")
                output = result.outputs[0]
                assert not isinstance(output.content, bytes)
                assert output.metadata["transferVerified"] is True
                relative = storage.write_output("project", "job", output.filename, output.content)
                path = storage.resolve("project", relative)
                assert path.stat().st_size == size
                with path.open("rb") as saved:
                    assert hashlib.file_digest(saved, "sha256").hexdigest() == digest.hexdigest()
                _, peak = tracemalloc.get_traced_memory()
                assert peak < 32 * 1024 * 1024, f"Unexpected buffering: {peak} bytes"
            finally:
                if result is not None:
                    result.close()
                tracemalloc.stop()
            assert output.content.closed
            print(json.dumps({
                "bytes": size, "pythonPeakBytes": peak, "sha256": digest.hexdigest(),
                "transferVerified": True, "temporaryStreamClosed": True,
            }))


if __name__ == "__main__":
    asyncio.run(main())
