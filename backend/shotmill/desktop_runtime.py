"""Private loopback server owned by the desktop launcher's stdin pipe."""

import argparse
import json
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from shotmill.desktop_app import create_desktop_app
from shotmill.desktop_lock import desktop_data_lock
from shotmill.desktop_media import configure_bundled_media_tools


class DesktopServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if self.started and not self.should_exit:
            port = sockets[0].getsockname()[1]
            print(json.dumps({"event": "ready", "url": f"http://127.0.0.1:{port}"}),
                  flush=True)


def main():
    parser = argparse.ArgumentParser(description="ShotMill desktop backend")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--frontend-root", type=Path, required=True)
    args = parser.parse_args()
    configure_bundled_media_tools()
    with desktop_data_lock(args.data_root.resolve()):
        run_server(args.data_root, args.frontend_root)


def run_server(data_root: Path, frontend_root: Path):
    application = create_desktop_app(data_root, frontend_root)
    server = DesktopServer(uvicorn.Config(
        application, host="127.0.0.1", port=0, access_log=False, log_level="warning",
    ))

    def watch_parent():
        # The launcher keeps this pipe open for its lifetime. EOF also covers a
        # launcher crash, without assuming a parent PID cannot be reused.
        while sys.stdin.buffer.read(1):
            pass
        server.should_exit = True

    threading.Thread(target=watch_parent, daemon=True, name="desktop-parent").start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Keep ownership of the OS-selected port throughout startup.
        listener.bind(("127.0.0.1", 0))
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
