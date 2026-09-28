import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_process_ready_parent_exit_and_reopen(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("Packaged frontend", encoding="utf-8")
    data = tmp_path / "desktop-data"
    wrong = tmp_path / "development-data"
    environment = {
        **os.environ, "PYTHONPATH": str(ROOT / "backend"),
        "SHOTMILL_DATA_ROOT": str(wrong),
        "SHOTMILL_DATABASE_URL": f"sqlite:///{(wrong / 'wrong.db').as_posix()}",
        "PYTHONIOENCODING": "utf-8",
    }
    for reopening, crash in ((False, False), (True, True), (True, False)):
        with (tmp_path / "runtime.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "shotmill.desktop_runtime",
                 "--data-root", str(data), "--frontend-root", str(frontend)],
                cwd=tmp_path, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            lines = queue.Queue()
            reader = threading.Thread(
                target=lambda lines=lines, process=process: lines.put(process.stdout.readline()),
                daemon=True,
            )
            reader.start()
            try:
                ready = json.loads(lines.get(timeout=30))
                assert ready["event"] == "ready"
                assert ready["url"].startswith("http://127.0.0.1:")
                duplicate = subprocess.run(
                    [sys.executable, "-m", "shotmill.desktop_runtime",
                     "--data-root", str(data), "--frontend-root", str(frontend)],
                    cwd=tmp_path, env=environment, input="", capture_output=True,
                    text=True, encoding="utf-8", timeout=20,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert duplicate.returncode != 0
                assert "请勿重复启动" in duplicate.stderr
                assert duplicate.stdout == ""
                with httpx.Client(base_url=ready["url"], trust_env=False) as client:
                    assert client.get("/health").status_code == 200
                    assert client.get("/").text == "Packaged frontend"
                    if reopening:
                        assert "Persisted desktop project" in client.get("/api/v1/projects").text
                    else:
                        response = client.post("/api/v1/projects", json={
                            "title": "Persisted desktop project",
                        })
                        assert response.status_code == 201, response.text
                if crash:
                    process.kill()
                    assert process.wait(timeout=20) != 0
                else:
                    process.stdin.close()
                    assert process.wait(timeout=20) == 0
                assert not wrong.exists()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                if not process.stdin.closed:
                    process.stdin.close()
                reader.join(timeout=2)
                process.stdout.close()
