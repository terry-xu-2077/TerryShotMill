from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL_7 = Path(r"C:\Program Files\PowerShell\7\pwsh.exe")
LAUNCHER = ROOT / "scripts" / "start-dev.ps1"
MOCK_LAUNCHER = ROOT / "scripts" / "start-mock-ui.ps1"
BACKEND_RUNNER = ROOT / "scripts" / "run-backend.ps1"
REUSE_CONFIG = ROOT / "frontend" / "src-tauri" / "tauri.reuse-dev.conf.json"


class _ProbeHandler(BaseHTTPRequestHandler):
    body = b""
    content_type = "text/html; charset=utf-8"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(200)
        self.send_header("Content-Type", self.content_type)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _ShotMillBackendProbe(_ProbeHandler):
    body = b'{"status":"ok","service":"shotmill-backend"}'
    content_type = "application/json; charset=utf-8"


@pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL_7.exists(), reason="Windows launcher")
@pytest.mark.parametrize(
    ("body", "expected_code", "expected_text"),
    [
        (
            b'<title>ShotMill</title><script type="module" src="/src/main.tsx"></script>',
            0,
            "a second Vite server will not be started",
        ),
        (b"<title>Another application</title>", 1, "it is not the ShotMill frontend"),
    ],
)
def test_launcher_handles_an_occupied_frontend_port(
    body: bytes,
    expected_code: int,
    expected_text: str,
) -> None:
    frontend_handler = type("LauncherProbeHandler", (_ProbeHandler,), {"body": body})
    frontend_server = ThreadingHTTPServer(("127.0.0.1", 0), frontend_handler)
    backend_server = ThreadingHTTPServer(("127.0.0.1", 0), _ShotMillBackendProbe)
    frontend_thread = threading.Thread(target=frontend_server.serve_forever, daemon=True)
    backend_thread = threading.Thread(target=backend_server.serve_forever, daemon=True)
    frontend_thread.start()
    backend_thread.start()
    try:
        completed = subprocess.run(
            [
                str(POWERSHELL_7),
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(LAUNCHER),
                "-CheckOnly",
                "-DevPort",
                str(frontend_server.server_port),
                "-BackendPort",
                str(backend_server.server_port),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    finally:
        frontend_server.shutdown()
        backend_server.shutdown()
        frontend_server.server_close()
        backend_server.server_close()
        frontend_thread.join(timeout=5)
        backend_thread.join(timeout=5)

    assert completed.returncode == expected_code
    assert expected_text in f"{completed.stdout}\n{completed.stderr}"


def test_launcher_contains_managed_visible_backend_lifecycle() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8")
    runner = BACKEND_RUNNER.read_text(encoding="utf-8")

    assert "Start-ShotMillBackend" in launcher
    assert "Wait-BackendReady" in launcher
    assert "Stop-ShotMillBackend" in launcher
    assert "WindowStyle Normal" in launcher
    assert '$env:VITE_SHOTMILL_API_BASE_URL = "$BackendBaseUrl/api/v1"' in launcher
    assert "backend-lifecycle.log" in launcher

    assert "ShotMill Backend" in runner
    assert "shotmill.app:app" in runner
    assert "--reload" in runner
    assert "ParentProcessId" in runner
    assert "launcher process disappeared; stopping backend process tree" in runner
    assert "taskkill.exe /PID" in runner


@pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL_7.exists(), reason="Windows launcher")
def test_mock_launcher_falls_back_when_the_requested_ui_port_is_occupied() -> None:
    occupied_server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    occupied_thread = threading.Thread(target=occupied_server.serve_forever, daemon=True)
    occupied_thread.start()
    try:
        completed = subprocess.run(
            [
                str(POWERSHELL_7),
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(MOCK_LAUNCHER),
                "-CheckOnly",
                "-DevPort",
                str(occupied_server.server_port),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    finally:
        occupied_server.shutdown()
        occupied_server.server_close()
        occupied_thread.join(timeout=5)

    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0
    assert "is already in use; using UI port" in output
    assert "[CHECK] Mock launcher preflight passed." in output


def test_mock_launcher_only_cleans_verified_project_services() -> None:
    launcher = MOCK_LAUNCHER.read_text(encoding="utf-8")

    assert "Stop-VerifiedResidual" in launcher
    assert "Test-ShotMillFrontendPort" in launcher
    assert "Test-ShotMillMockApiPort" in launcher
    assert "[regex]::Escape($Root)" in launcher
    assert "$Owner.Name -eq 'node.exe'" in launcher
    assert "$Owner.Name -eq 'python.exe'" in launcher
    assert "mock-ui-processes.json" in launcher
    assert "startTimeUtcTicks" in launcher
    assert "Stop-TrackedResidual" in launcher


def test_tauri_reuse_config_disables_the_duplicate_frontend_command() -> None:
    config = json.loads(REUSE_CONFIG.read_text(encoding="utf-8"))

    assert config["build"]["beforeDevCommand"] is None
