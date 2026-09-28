import os
import sys

import pytest
from shotmill.desktop_media import configure_bundled_media_tools


def test_development_does_not_change_media_search_path(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("PATH", "developer-tools")
    configure_bundled_media_tools()
    assert os.environ["PATH"] == "developer-tools"


def test_installed_app_requires_both_tools_before_changing_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("PATH", "developer-tools")
    tools = tmp_path / "media-tools"
    tools.mkdir()
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        with pytest.raises(RuntimeError, match=name):
            configure_bundled_media_tools()
        assert os.environ["PATH"] == "developer-tools"
        (tools / name).write_bytes(b"test fixture")
    configure_bundled_media_tools()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tools)
