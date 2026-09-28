"""Test-only HTTP fault proxy: lose one accepted submission response, then reconnect."""

import json
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


class DisconnectState:
    def __init__(self):
        self.interrupted = threading.Event()
        self.reconnect = threading.Event()
        self.submissions: list[str] = []
        self.blocked_reads = 0
        self.lock = threading.Lock()


@contextmanager
def disconnect_proxy(upstream: str):
    state = DisconnectState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def cut_connection(self):
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()

        def forward(self):
            if self.headers.get("Upgrade"):
                self.send_error(400, "HTTP-only acceptance proxy")
                return
            if state.interrupted.is_set() and not state.reconnect.is_set():
                with state.lock:
                    state.blocked_reads += 1
                self.cut_connection()
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with httpx.Client(trust_env=False, timeout=20) as client:
                response = client.request(
                    self.command, upstream.rstrip("/") + self.path, content=body,
                    headers={"Content-Type": self.headers.get("Content-Type", "application/json")},
                )
            if self.command == "POST" and self.path == "/terryflow/v1/jobs":
                with state.lock:
                    state.submissions.append(json.loads(body)["jobId"])
                if response.is_success and not state.interrupted.is_set():
                    state.interrupted.set()
                    self.cut_connection()
                    return
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() not in {
                    "transfer-encoding", "connection", "content-encoding", "content-length",
                }:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.content)

        do_GET = do_POST = do_HEAD = forward

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        state.reconnect.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
