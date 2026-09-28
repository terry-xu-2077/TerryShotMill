"""Short-lived, single-use downloads of already completed project packages.

Preparation errors reach the UI as JSON before a native browser download starts.
The browser never needs to buffer a multi-gigabyte ZIP in renderer memory.
"""

import secrets
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Timer

from shotmill.application.project_export_service import ProjectExportService
from shotmill.errors import ConflictError, NotFoundError


@dataclass
class PreparedDownload:
    path: Path
    lifetime: ExitStack
    timer: Timer


class ProjectExportDownloads:
    def __init__(self, exporter: ProjectExportService, *, ttl_seconds=300, max_pending=2):
        self.exporter = exporter
        self.ttl_seconds = ttl_seconds
        self.max_pending = max_pending
        self._lock = Lock()
        self._pending: dict[str, PreparedDownload] = {}
        self._preparing = 0
        self._closed = False

    def prepare(self, project_id: str) -> str:
        with self._lock:
            if self._closed or self._preparing + len(self._pending) >= self.max_pending:
                raise ConflictError("PROJECT_EXPORT_BUSY", "已有项目正在准备下载，请稍后重试。")
            self._preparing += 1
        lifetime = ExitStack()
        try:
            path = lifetime.enter_context(self.exporter.prepare(project_id))
            token = secrets.token_urlsafe(32)
            timer = Timer(self.ttl_seconds, self.discard, args=(token,))
            timer.daemon = True
            with self._lock:
                if self._closed:
                    raise ConflictError("PROJECT_EXPORT_CLOSED", "应用正在退出，请重新启动后导出。")
                self._pending[token] = PreparedDownload(path, lifetime, timer)
                try:
                    timer.start()
                except BaseException:
                    self._pending.pop(token)
                    raise
            return token
        except BaseException:
            lifetime.close()
            raise
        finally:
            with self._lock:
                self._preparing -= 1

    def claim(self, token: str) -> tuple[Path, ExitStack]:
        with self._lock:
            download = self._pending.pop(token, None)
        if download is None:
            raise NotFoundError("PROJECT_EXPORT_EXPIRED", "下载已过期或已开始，请重新导出。")
        download.timer.cancel()
        # The response now owns cleanup, including disconnects; expiration must
        # never delete a package that the browser is actively receiving.
        return download.path, download.lifetime

    def discard(self, token: str) -> None:
        with self._lock:
            download = self._pending.pop(token, None)
        if download:
            download.timer.cancel()
            download.lifetime.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            downloads = list(self._pending.values())
            self._pending.clear()
        with ExitStack() as cleanup:
            for download in downloads:
                download.timer.cancel()
                cleanup.callback(download.lifetime.close)
