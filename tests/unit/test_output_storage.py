import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import pytest
from shotmill.media.storage import MediaStorage


def test_output_stream_is_copied_in_bounded_chunks(tmp_path):
    class BoundedStream(BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 1024 * 1024
            return super().read(size)

    content = b"video" * 600_000
    stream = BoundedStream(content)
    storage = MediaStorage(tmp_path)
    relative = storage.write_output("project", "job", "clip.mp4", stream)
    assert storage.resolve("project", relative).read_bytes() == content
    assert not stream.closed
    assert storage.write_output("project", "job", "clip.mp4", content) == relative


def test_interrupted_output_stream_does_not_publish_partial_bytes(tmp_path):
    class BrokenStream(BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("input interrupted")
            return super().read(size)

    storage = MediaStorage(tmp_path)
    with pytest.raises(OSError, match="interrupted"):
        storage.write_output("project", "job", "clip.mp4", BrokenStream(b"partial"))
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_same_output_name_never_overwrites_previous_content(tmp_path):
    storage = MediaStorage(tmp_path)
    first = storage.write_output("project", "job", "clip.mp4", b"first")
    second = storage.write_output("project", "job", "clip.mp4", b"second")
    assert first != second
    assert storage.resolve("project", first).read_bytes() == b"first"
    assert storage.resolve("project", second).read_bytes() == b"second"
    assert storage.write_output("project", "job", "clip.mp4", b"first") == first


def test_sanitized_output_names_cannot_destroy_each_other(tmp_path):
    storage = MediaStorage(tmp_path)
    first = storage.write_output("project", "job", "clip?.mp4", b"first")
    second = storage.write_output("project", "job", "clip*.mp4", b"second")
    assert first != second
    assert storage.resolve("project", first).read_bytes() == b"first"


def test_existing_damaged_output_is_not_silently_replaced(tmp_path):
    storage = MediaStorage(tmp_path)
    relative = storage.write_output("project", "job", "clip.mp4", b"original")
    path = storage.resolve("project", relative)
    path.write_bytes(b"damaged")
    with pytest.raises(OSError, match="damaged"):
        storage.write_output("project", "job", "clip.mp4", b"original")
    assert path.read_bytes() == b"damaged"


def test_concurrent_output_collection_is_idempotent(tmp_path):
    storage = MediaStorage(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as workers:
        paths = list(workers.map(
            lambda _: storage.write_output("project", "job", "clip.mp4", b"result"),
            range(8),
        ))
    assert len(set(paths)) == 1
    assert storage.resolve("project", paths[0]).read_bytes() == b"result"
    assert not list(tmp_path.rglob(".pending-*"))


def test_failed_publication_leaves_no_partial_output(tmp_path, monkeypatch):
    storage = MediaStorage(tmp_path)

    def fail_link(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="disk failure"):
        storage.write_output("project", "job", "clip.mp4", b"result")
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.skipif(os.name != "nt", reason="Windows extended path spelling")
def test_extended_path_spelling_preserves_boundary_checks(tmp_path, monkeypatch):
    storage = MediaStorage(tmp_path)
    root = storage.project_root("project")
    original_resolve = Path.resolve

    def extended_resolve(path, *args, **kwargs):
        result = original_resolve(path, *args, **kwargs)
        if result != root:
            return Path("\\\\?\\" + str(result))
        return result

    monkeypatch.setattr(Path, "resolve", extended_resolve)
    assert storage.resolve("project", "outputs/clip.mp4") == root / "outputs/clip.mp4"
    with pytest.raises(ValueError, match="escapes"):
        storage.resolve("project", "../outside.mp4")
