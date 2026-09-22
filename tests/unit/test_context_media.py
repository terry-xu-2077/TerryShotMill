import json
import subprocess

import pytest
from shotmill.errors import ShotMillError
from shotmill.media.context import prepare_context_media, video_duration
from shotmill.media.storage import MediaStorage


def test_last_frame_and_last_second_are_extracted_from_changing_video(tmp_path):
    storage = MediaStorage(tmp_path)
    source = storage.resolve("p", "source.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=32x24:rate=24:duration=2",
            "-c:v",
            "libx264",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    tail = prepare_context_media(storage, "p", "result", "source.mp4", "尾帧承接", None, None)

    def pixels(path, filter):
        return subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-vf",
                filter,
                "-frames:v",
                "1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "-",
            ],
            check=True,
            capture_output=True,
        ).stdout

    assert pixels(storage.resolve("p", tail["projectRelativePath"]), "null") == pixels(
        source, "select=eq(n\\,47)"
    )
    segment = prepare_context_media(storage, "p", "result", "source.mp4", "片段承接", 1, 2)
    clip = storage.resolve("p", segment["projectRelativePath"])
    assert video_duration(clip) == pytest.approx(1, abs=0.001)
    streams = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,nb_frames",
                "-of",
                "json",
                str(clip),
            ],
            check=True,
            capture_output=True,
        ).stdout
    )["streams"]
    assert streams == [{"codec_type": "video", "nb_frames": "24"}]
    with pytest.raises(ShotMillError, match="实际时长"):
        prepare_context_media(storage, "p", "result", "source.mp4", "片段承接", 5, 6)
    # A replacement at the same path must not retain a cached duration from the old video.
    source.write_bytes(clip.read_bytes())
    assert video_duration(source) == pytest.approx(1, abs=0.001)
