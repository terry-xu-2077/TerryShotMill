from shotmill.media.storage import MediaStorage


def test_mapped_reads_do_not_redirect_legacy_writes(tmp_path):
    blob = tmp_path / "immutable"
    blob.write_bytes(b"original")
    storage = MediaStorage(tmp_path / "projects", read_resolver=lambda *_: blob)
    relative, _ = storage.write_asset("project", "asset", "sample.png", b"new")
    assert storage.resolve_read("project", relative) == blob
    assert storage.resolve("project", relative).read_bytes() == b"new"
    assert blob.read_bytes() == b"original"
    output = storage.write_output("project", "job", "clip.mp4", b"video")
    assert storage.resolve("project", output).read_bytes() == b"video"
    assert blob.read_bytes() == b"original"


def test_read_resolution_without_mapping_preserves_legacy_behavior(tmp_path):
    storage = MediaStorage(tmp_path)
    relative, _ = storage.write_asset("project", "asset", "sample.png", b"image")
    assert storage.resolve_read("project", relative).read_bytes() == b"image"
