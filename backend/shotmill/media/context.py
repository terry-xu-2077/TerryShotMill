"""Local, content-addressed media prepared for immutable generation context."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from shotmill.errors import ShotMillError
from shotmill.media.storage import MediaStorage


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _run(tool: str, arguments: list[str]) -> bytes:
    executable = shutil.which(tool)
    if not executable:
        raise ShotMillError(
            "CONTEXT_TOOL_UNAVAILABLE", "缺少视频处理工具，无法准备上下文媒体。", 503
        )
    try:
        return subprocess.run(
            [executable, *arguments],
            check=True,
            capture_output=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise ShotMillError(
            "CONTEXT_MEDIA_INVALID", "上下文视频读取或截取失败，请检查来源视频。", 422
        ) from exc


def video_duration(path: Path) -> float:
    try:
        stat = path.stat()
    except OSError as exc:
        raise ShotMillError("CONTEXT_MEDIA_MISSING", "视频文件不存在或无法读取。", 409) from exc
    return _probe_video_duration(path.resolve(), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=256)
def _probe_video_duration(path: Path, modified_ns: int, size: int) -> float:
    # Key by file state so repeated workspace reads do not launch a probe per video.
    raw = _run(
        "ffprobe",
        [
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=duration:format=duration",
            "-of",
            "json",
            str(path),
        ],
    )
    try:
        info = json.loads(raw)
        stream = info["streams"][0]
        duration = float(stream.get("duration", info.get("format", {}).get("duration")))
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid duration")
        return duration
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ShotMillError("CONTEXT_MEDIA_INVALID", "上下文来源没有有效的视频时长。", 422) from exc


def prepare_context_media(
    storage: MediaStorage,
    project_id: str,
    result_id: str,
    relative_source: str,
    mode: str,
    start: float | None,
    end: float | None,
) -> dict:
    source = storage.resolve(project_id, relative_source)
    if not source.is_file():
        raise ShotMillError("CONTEXT_MEDIA_MISSING", "上下文来源视频文件不存在。", 409)
    duration = video_duration(source)
    segment = mode == "片段承接"
    if segment:
        end = duration if end is None else float(end)
        start = max(0, end - 1) if start is None else float(start)
        if not (
            math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration + 1e-6
        ):
            raise ShotMillError("INVALID_CONTEXT_RANGE", "承接区间超出来源视频的实际时长。", 422)
    else:
        start = end = None
    source_digest = file_digest(source)
    key = hashlib.sha256(json.dumps([source_digest, mode, start, end, "v1"]).encode()).hexdigest()
    suffix = ".mp4" if segment else ".png"
    relative = f"context/{key}{suffix}"
    destination = storage.resolve(project_id, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Regenerate into a unique temporary file; concurrent preflights never see partial output.
    temporary = destination.with_name(f"{key}-{uuid4().hex}{suffix}")
    try:
        args = ["-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe"]
        if segment:
            args += [
                "-ss",
                str(start),
                "-i",
                str(source),
                "-t",
                str(end - start),
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ]
        else:
            # Decode the last second and reverse it so the first output is the exact last frame.
            args += [
                "-sseof",
                "-1",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-vf",
                "reverse",
                "-frames:v",
                "1",
                "-update",
                "1",
            ]
        _run("ffmpeg", [*args, str(temporary)])
        if not temporary.is_file() or not temporary.stat().st_size:
            raise ShotMillError("CONTEXT_MEDIA_INVALID", "上下文媒体截取结果为空。", 422)
        if file_digest(source) != source_digest:
            raise ShotMillError("CONTEXT_SOURCE_CHANGED", "上下文视频已变化，请重新提交。", 409)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "assetId": f"context-{key}",
        "sourceResultId": result_id,
        "sourceSha256": source_digest,
        "sourceDurationSeconds": duration,
        "startSeconds": start,
        "endSeconds": end,
        "audioIncluded": False,
        "projectRelativePath": relative,
        "originalFilename": destination.name,
        "mediaType": "video" if segment else "image",
        "role": "context_segment" if segment else "context_last_frame",
        "sha256": file_digest(destination),
    }
