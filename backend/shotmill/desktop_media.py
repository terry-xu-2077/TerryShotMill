"""Resolve media tools from the frozen bundle, never the developer's installation."""

import os
import sys
from pathlib import Path


def configure_bundled_media_tools() -> None:
    if not getattr(sys, "frozen", False):
        return
    tools = Path(sys._MEIPASS) / "media-tools"
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        if not (tools / name).is_file():
            raise RuntimeError(f"安装包缺少媒体工具 {name}，请重新安装 ShotMill。")
    os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")
