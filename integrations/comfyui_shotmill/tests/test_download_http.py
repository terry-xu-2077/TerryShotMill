"""Real aiohttp FileResponse tests; run with ComfyUI's Python (no GPU imports)."""

import ast
import asyncio
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer


class DownloadHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_response_digest_and_index_boundary_over_http(self):
        source = Path(__file__).resolve().parents[1] / "bridge_api.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body
                     if isinstance(node, ast.AsyncFunctionDef) and node.name == "_result_file"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            block = bytes(range(256)) * 4096
            digest = hashlib.sha256()
            with (root / "clip.mp4").open("wb") as output:
                for _ in range(32):
                    output.write(block)
                    digest.update(block)
            scope = {
                "web": web, "asyncio": asyncio, "hashlib": hashlib, "Path": Path,
                "JOB_INDEX": None,
                "_safe_name": lambda value, fallback: value,
                "_load_index": lambda _: {"jobs": {"job": {}}},
                "_job_state": lambda _: {"results": [{"filename": "clip.mp4"}]},
                "folder_paths": SimpleNamespace(get_output_directory=lambda: directory),
            }
            exec(compile(tree, str(source), "exec"), scope)
            app = web.Application()
            app.router.add_get("/results/{job_id}/files/{index}", scope["_result_file"])
            async with TestServer(app, host="127.0.0.1") as server:
                async with aiohttp.ClientSession() as client:
                    async with client.get(server.make_url("/results/job/files/0")) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["X-Content-SHA256"], digest.hexdigest())
                        received, size = hashlib.sha256(), 0
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            received.update(chunk)
                            size += len(chunk)
                        self.assertEqual(size, 32 * len(block))
                        self.assertEqual(received.hexdigest(), digest.hexdigest())
                    for suffix in ("job/files/-1", "job/files/1", "missing/files/0"):
                        async with client.get(server.make_url("/results/" + suffix)) as response:
                            self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
