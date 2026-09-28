import hashlib
import os

import pytest
from shotmill.media.import_storage import ImportStorage


def test_import_streams_independent_copy_and_checks_hash(tmp_path):
    source = tmp_path / "source.mp4"
    content = b"video" * 500000
    source.write_bytes(content)
    storage = ImportStorage(tmp_path / "projects")
    checksum = hashlib.sha256(content).hexdigest()
    assert storage.copy(source, "p", "assets/copy.mp4", expected_hash=checksum) == checksum
    source.write_bytes(b"source changed")
    destination = storage.managed.resolve("p", "assets/copy.mp4")
    assert destination.read_bytes() == content
    assert not list(destination.parent.glob(".import-*"))
    with pytest.raises(FileExistsError):
        storage.copy(source, "p", "assets/copy.mp4")
    assert destination.read_bytes() == content


def test_import_rejects_bad_checksum_and_empty_input(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    storage = ImportStorage(tmp_path / "projects")
    with pytest.raises(ValueError, match="checksum"):
        storage.copy(source, "p", "assets/copy.mp4", expected_hash="wrong")
    source.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        storage.copy(source, "p", "assets/copy.mp4")
    assert storage.managed.files("p") == set()


def test_import_write_failure_cleans_temporary_and_retains_source(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    storage = ImportStorage(tmp_path / "projects")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="disk full"):
        storage.copy(source, "p", "assets/copy.mp4")
    assert storage.managed.files("p") == set()
    assert source.read_bytes() == b"video"
