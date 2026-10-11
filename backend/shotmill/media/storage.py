from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from shotmill.errors import ShotMillError

_SAFE_NAME_RE = re.compile(r"[^\w.()\-\u4e00-\u9fff]+", re.UNICODE)


def safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", Path(name).name).strip("._")
    return cleaned or "asset.bin"


def _resolved_path(path: Path) -> Path:
    resolved = str(path.resolve())
    # Windows may retain the extended prefix when a concurrently opened file
    # cannot be queried. Normalize spelling, not the resolved filesystem target.
    if os.name == "nt":
        if resolved.startswith("\\\\?\\UNC\\"):
            resolved = "\\\\" + resolved[8:]
        elif resolved.startswith("\\\\?\\") and resolved[5:7] == ":\\":
            resolved = resolved[4:]
    return Path(resolved)


class MediaStorage:
    def __init__(
        self, projects_root: Path, *, shared_resolver: Callable[[str, str], Path] | None = None,
        read_resolver: Callable[[str, str], Path] | None = None,
        project_root_resolver: Callable[[str], Path] | None = None,
    ) -> None:
        self.shared_resolver = shared_resolver
        self.read_resolver = read_resolver
        self.project_root_resolver = project_root_resolver
        self.projects_root = projects_root
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str) -> Path:
        root = _resolved_path(
            self.project_root_resolver(project_id) if self.project_root_resolver
            else self.projects_root / project_id
        )
        return root

    def ensure_project_layout(self, project_id: str) -> None:
        root = self.project_root(project_id)
        root.mkdir(parents=True, exist_ok=True)
        for folder in ("assets", "thumbnails", "outputs", "context", "cache"):
            (root / folder).mkdir(parents=True, exist_ok=True)

    def write_asset(
        self,
        project_id: str,
        asset_id: str,
        original_filename: str,
        content: bytes,
    ) -> tuple[str, str]:
        self.ensure_project_layout(project_id)
        filename = f"{asset_id}_{safe_filename(original_filename)}"
        relative = PurePosixPath("assets") / filename
        path = self.resolve(project_id, relative.as_posix())
        path.write_bytes(content)
        return relative.as_posix(), hashlib.sha256(content).hexdigest()

    def write_output(
        self, project_id: str, job_id: str, filename: str, content: bytes | BinaryIO
    ) -> str:
        self.ensure_project_layout(project_id)
        directory = self.resolve(project_id, (PurePosixPath("outputs") / job_id).as_posix())
        directory.mkdir(parents=True, exist_ok=True)
        incoming = BytesIO(content) if isinstance(content, bytes) else content
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=".pending-", delete=False
            ) as outgoing:
                temporary = Path(outgoing.name)
                digest = hashlib.sha256()
                while chunk := incoming.read(1024 * 1024):
                    outgoing.write(chunk)
                    digest.update(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            checksum = digest.hexdigest()
            relative = PurePosixPath("outputs") / job_id / checksum / safe_filename(filename)
            path = self.resolve(project_id, relative.as_posix())
            path.parent.mkdir(parents=True, exist_ok=True)
            # Publish complete bytes without replacing an existing immutable result.
            try:
                os.link(temporary, path)
            except FileExistsError:
                with path.open("rb") as existing:
                    actual = hashlib.file_digest(existing, "sha256").hexdigest()
                if actual != checksum:
                    raise OSError("Existing output content is damaged") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return relative.as_posix()

    def resolve_read(self, project_id: str, project_relative_path: str) -> Path:
        """Resolve logical media for reading, never for creating or deleting files."""
        if self.read_resolver is not None:
            return self.read_resolver(project_id, project_relative_path)
        return self.resolve(project_id, project_relative_path)

    def resolve(self, project_id: str, project_relative_path: str) -> Path:
        if project_relative_path.startswith("shared/"):
            if self.shared_resolver is None:
                raise ValueError("Shared file resolver is not configured")
            return self.shared_resolver(project_id, project_relative_path)
        project_root = self.project_root(project_id)
        candidate = _resolved_path(project_root / Path(project_relative_path))
        try:
            candidate.relative_to(project_root)
        except ValueError as exc:
            raise ValueError("Path escapes project storage root") from exc
        return candidate

    def video_thumbnail(self, project_id: str, relative_path: str, *, seconds: float = 0) -> str:
        source = self.resolve_read(project_id, relative_path)
        if not math.isfinite(seconds) or seconds < 0:
            raise ShotMillError("FRAME_TIME_INVALID", "截帧时间无效。", 422)
        if not source.is_file():
            raise ShotMillError("MEDIA_NOT_FOUND", "视频文件不存在。", 404)
        stat = source.stat()
        key = hashlib.sha256(
            f"{relative_path}|{stat.st_size}|{stat.st_mtime_ns}|{seconds:.6f}".encode()
        ).hexdigest()
        relative = f"thumbnails/{key}.png"
        destination = self.resolve(project_id, relative)
        if destination.is_file():
            return relative
        executable = shutil.which("ffmpeg")
        if not executable:
            raise ShotMillError("FRAME_TOOL_UNAVAILABLE", "缺少 FFmpeg，无法截取视频封面。", 503)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{key}-{uuid4().hex}.png")
        try:
            subprocess.run(
                [executable, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                 "-ss", str(seconds), "-i", str(source), "-frames:v", "1",
                 "-vf", "scale=960:960:force_original_aspect_ratio=decrease",
                 "-update", "1", str(temporary)],
                check=True, capture_output=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if not temporary.is_file() or not temporary.stat().st_size:
                raise ShotMillError("FRAME_UNAVAILABLE", "该时间点没有可用画面，请重新选择。", 422)
            temporary.replace(destination)
        except (subprocess.SubprocessError, OSError) as exc:
            raise ShotMillError(
                "FRAME_UNAVAILABLE", "视频截帧失败，请检查视频后重试。", 422
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
        return relative

    @staticmethod
    def media_url(project_id: str, project_relative_path: str) -> str:
        return f"/media/{project_id}/{PurePosixPath(project_relative_path).as_posix()}"
