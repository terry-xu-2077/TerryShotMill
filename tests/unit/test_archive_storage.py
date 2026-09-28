import os

import pytest
from shotmill.media.archive_storage import ArchiveStorage


def test_archive_is_independent_verified_and_deduplicated(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video" * 300000)
    storage = ArchiveStorage(tmp_path / "archive")
    first = storage.copy(source)
    assert storage.copy(source) == first
    assert source.exists()
    source.unlink()
    assert storage.verify(first)
    assert storage.resolve(first["path"]).read_bytes() == b"video" * 300000
    assert not list(storage.root.glob(".pending-*"))


def test_failed_copy_preserves_source_and_cleans_temporary(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    storage = ArchiveStorage(tmp_path / "archive")

    def fail_sync(*args):
        raise OSError("injected disk full")

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(OSError, match="disk full"):
        storage.copy(source)
    assert source.read_bytes() == b"video"
    assert list(storage.root.iterdir()) == []


def test_archive_detects_corruption_and_rejects_escape(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    storage = ArchiveStorage(tmp_path / "archive")
    file = storage.copy(source)
    storage.resolve(file["path"]).write_bytes(b"damaged")
    assert not storage.verify(file)
    with pytest.raises(OSError, match="damaged"):
        storage.copy(source)
    with pytest.raises(ValueError):
        storage.resolve("../outside")
    assert not storage.verify({**file, "path": "../source.mp4"})
    assert source.read_bytes() == b"video"
    assert not list(storage.root.glob(".pending-*"))
