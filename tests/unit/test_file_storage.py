from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from shotmill.media.file_storage import FileStorage


def test_shared_store_deduplicates_without_project_identity(tmp_path):
    storage = FileStorage(tmp_path)
    first = storage.put(BytesIO(b"same media"))
    second = storage.put(BytesIO(b"same media"))
    assert first == second
    assert storage.resolve(first).read_bytes() == b"same media"
    assert len([path for path in tmp_path.rglob("*") if path.is_file()]) == 1


def test_different_content_does_not_overwrite_existing_file(tmp_path):
    storage = FileStorage(tmp_path)
    first = storage.put(BytesIO(b"first"))
    second = storage.put(BytesIO(b"second"))
    assert first.sha256 != second.sha256
    assert storage.resolve(first).read_bytes() == b"first"


def test_failed_checksum_never_publishes_and_cleans_staging(tmp_path):
    storage = FileStorage(tmp_path)
    with pytest.raises(ValueError, match="checksum"):
        storage.put(BytesIO(b"bad"), expected_hash="0" * 64)
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_existing_corrupt_shared_file_is_not_silently_reused(tmp_path):
    storage = FileStorage(tmp_path)
    file = storage.put(BytesIO(b"correct"))
    storage.resolve(file).write_bytes(b"damaged")
    with pytest.raises(OSError, match="damaged"):
        storage.put(BytesIO(b"correct"))


def test_concurrent_writers_publish_one_shared_object(tmp_path):
    storage = FileStorage(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as workers:
        files = list(workers.map(lambda _: storage.put(BytesIO(b"shared")), range(12)))
    assert len(set(files)) == 1
    assert len([path for path in tmp_path.rglob("*") if path.is_file()]) == 1


def test_source_copy_is_independent_of_external_file(tmp_path):
    source = tmp_path / "external"
    source.write_bytes(b"source")
    storage = FileStorage(tmp_path / "library")
    with source.open("rb") as stream:
        file = storage.put(stream)
    source.write_bytes(b"changed")
    assert storage.resolve(file).read_bytes() == b"source"
