"""Smoke-test a frozen Windows backend without a Python development environment."""

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
from pathlib import Path

import httpx


def verify(executable: Path) -> None:
    executable = executable.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="shotmill-frozen-smoke-") as temporary:
        root = Path(temporary)
        frontend = root / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("Frozen ShotMill", encoding="utf-8")
        environment = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("PYTHON", "SHOTMILL", "VIRTUAL_ENV"))
        }
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        tools = executable.parent / "_internal" / "media-tools"
        video = root / "media-smoke.mp4"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run([
            str(tools / "ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i",
            "color=c=blue:s=32x32:d=0.2", "-c:v", "mpeg4", str(video),
        ], env=environment, cwd=root, check=True, capture_output=True,
            timeout=30, creationflags=flags)
        probe = subprocess.run([
            str(tools / "ffprobe.exe"), "-v", "error", "-show_entries",
            "stream=width,height", "-of", "json", str(video),
        ], env=environment, cwd=root, check=True, capture_output=True,
            timeout=30, creationflags=flags)
        stream = json.loads(probe.stdout)["streams"][0]
        assert (stream["width"], stream["height"]) == (32, 32)
        package = None
        original_id = None
        for reopening in (False, True):
            with (root / "backend.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [str(executable), "--data-root", str(root / "data"),
                     "--frontend-root", str(frontend)],
                    cwd=root, env=environment, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                lines = queue.Queue()
                reader = threading.Thread(
                    target=lambda lines=lines, process=process: lines.put(
                        process.stdout.readline()),
                    daemon=True,
                )
                reader.start()
                try:
                    line = lines.get(timeout=60)
                    if not line:
                        raise RuntimeError((root / "backend.log").read_text(encoding="utf-8"))
                    ready = json.loads(line)
                    if ready.get("event") != "ready":
                        raise RuntimeError(f"Unexpected startup response: {ready}")
                    with httpx.Client(base_url=ready["url"], trust_env=False) as client:
                        assert client.get("/health").status_code == 200
                        assert client.get("/").text == "Frozen ShotMill"
                        assert client.get("/shotmill.db").status_code == 404
                        if reopening:
                            assert "Frozen project" in client.get("/api/v1/projects").text
                            imported = client.post("/api/v1/projects/import", files={
                                "file": ("project.zip", package, "application/zip"),
                            })
                            assert imported.status_code == 201, imported.text
                            destination = imported.json()["projectId"]
                            assert destination != original_id
                            assets = client.get(
                                f"/api/v1/projects/{destination}/assets",
                            ).json()["items"]
                            assert len(assets) == 1
                            relative = assets[0]["projectRelativePath"]
                            assert client.get(f"/media/{destination}/{relative}").content == (
                                video.read_bytes()
                            )
                        else:
                            response = client.post("/api/v1/projects", json={
                                "title": "Frozen project",
                            })
                            assert response.status_code == 201, response.text
                            original_id = response.json()["id"]
                            with video.open("rb") as media:
                                uploaded = client.post(
                                    f"/api/v1/projects/{original_id}/assets",
                                    files={"file": ("sample.mp4", media, "video/mp4")},
                                )
                            assert uploaded.status_code == 201, uploaded.text
                            exported = client.get(f"/api/v1/projects/{original_id}/export")
                            assert exported.status_code == 200, exported.text
                            package = exported.content
                    process.stdin.close()
                    assert process.wait(timeout=30) == 0
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
                    if not process.stdin.closed:
                        process.stdin.close()
                    reader.join(timeout=2)
                    process.stdout.close()
        print("PASS frozen runtime: media, API, frontend, shutdown, persistence, project ZIP")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    verify(parser.parse_args().executable)
