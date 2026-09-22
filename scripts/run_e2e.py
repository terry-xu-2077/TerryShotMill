from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
HOST = "127.0.0.1"
FRONTEND_PORT = 1421


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind((HOST, 0))
        return int(listener.getsockname()[1])


def wait_for_server(process: subprocess.Popen[bytes], port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Vite exited before the E2E server became ready.")
        try:
            with socket.create_connection((HOST, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(
        f"E2E server on port {port} did not become ready within {timeout:.0f} seconds."
    )


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    # The Windows venv executable is a launcher with a real interpreter child.
    # Terminating only the launcher leaves uvicorn holding the temporary database.
    if sys.platform == "win32":
        stopped = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if stopped.returncode != 0:
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    node = shutil.which("node.exe" if sys.platform == "win32" else "node")
    if not node:
        raise RuntimeError("Node.js was not found on PATH.")

    vite_cli = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    playwright_cli = FRONTEND / "node_modules" / "@playwright" / "test" / "cli.js"
    for required in (vite_cli, playwright_cli):
        if not required.exists():
            raise RuntimeError(f"Missing frontend dependency: {required}")

    backend_port = available_port()
    with tempfile.TemporaryDirectory(prefix="shotmill-e2e-") as data_root:
        environment = os.environ.copy()
        python_paths = [str(ROOT / "backend"), str(ROOT / "scripts")]
        if environment.get("PYTHONPATH"):
            python_paths.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        environment["SHOTMILL_DATA_ROOT"] = data_root
        environment["SHOTMILL_BACKEND_URL"] = f"http://{HOST}:{backend_port}"

        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "e2e_backend:app",
                "--host",
                HOST,
                "--port",
                str(backend_port),
            ],
            cwd=ROOT / "scripts",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_server(backend, backend_port)
            frontend = subprocess.Popen(
                [
                    node,
                    str(vite_cli),
                    "--host",
                    HOST,
                    "--port",
                    str(FRONTEND_PORT),
                    "--strictPort",
                ],
                cwd=FRONTEND,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                wait_for_server(frontend, FRONTEND_PORT)
                environment["SHOTMILL_E2E_EXTERNAL_SERVER"] = "1"
                environment["SHOTMILL_E2E_BASE_URL"] = f"http://{HOST}:{FRONTEND_PORT}"
                completed = subprocess.run(
                    [node, str(playwright_cli), "test", *sys.argv[1:]],
                    cwd=FRONTEND,
                    env=environment,
                    check=False,
                )
                return completed.returncode
            finally:
                stop_process(frontend)
        finally:
            stop_process(backend)


if __name__ == "__main__":
    raise SystemExit(main())
