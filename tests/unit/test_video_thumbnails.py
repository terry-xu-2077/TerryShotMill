import shutil
import subprocess

import pytest
from shotmill.media.storage import MediaStorage


def test_video_frame_is_real_cached_image_and_preserves_source(tmp_path):
    storage = MediaStorage(tmp_path)
    source = storage.resolve("project", "clip.mp4")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "FFmpeg is required to verify real video thumbnails"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                    "color=c=orange:s=64x48:d=1", "-c:v", "mpeg4", str(source)], check=True)
    original = source.read_bytes()
    relative = storage.video_thumbnail("project", "clip.mp4", seconds=0.25)
    poster = storage.resolve("project", relative)
    assert poster.read_bytes().startswith(b"\x89PNG")
    stamp = poster.stat().st_mtime_ns
    assert storage.video_thumbnail("project", "clip.mp4", seconds=0.25) == relative
    assert poster.stat().st_mtime_ns == stamp
    assert source.read_bytes() == original
    with pytest.raises(ValueError):
        storage.video_thumbnail("project", "../outside.mp4")
