import os
from pathlib import Path

import pytest
from shotmill.media.cleanup_storage import CleanupStorage


@pytest.mark.parametrize("project,relative", [
    ("..", "file"), ("p", "../outside"), ("p", "C:/outside"),
    ("p", ""), ("p", "."), ("p", "outputs/../../outside"),
])
def test_cleanup_rejects_broad_or_escaping_paths(tmp_path, project, relative):
    storage = CleanupStorage(tmp_path / "projects")
    with pytest.raises(ValueError):
        storage.delete_file(project, relative)


def test_cleanup_handles_only_enumerated_files_and_preserves_neighbors(tmp_path):
    root = tmp_path / "projects"
    owned = root / "p" / "outputs" / "j"
    owned.mkdir(parents=True)
    (owned / "result.mp4").write_bytes(b"result")
    neighbor = root / "p" / "keep.mp4"
    neighbor.write_bytes(b"keep")
    storage = CleanupStorage(root)
    assert storage.files("p", "outputs/j") == {"outputs/j/result.mp4"}
    storage.delete_file("p", "outputs/j/result.mp4")
    storage.delete_file("p", "outputs/j/result.mp4")
    assert neighbor.read_bytes() == b"keep"
    assert storage.files("missing") == set()


def test_cleanup_refuses_linked_path(tmp_path, monkeypatch):
    from pathlib import Path

    root = tmp_path / "projects"
    (root / "p").mkdir(parents=True)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == "linked" or original(path))
    storage = CleanupStorage(root)
    with pytest.raises(ValueError, match="linked"):
        storage.delete_file("p", "linked/result.mp4")


@pytest.mark.skipif(os.name != "nt", reason="Windows extended path spelling")
def test_cleanup_normalizes_extended_paths_without_loosening_boundaries(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    (root / "p" / "outputs").mkdir(parents=True)
    source = root / "p" / "outputs" / "result.mp4"
    source.write_bytes(b"result")
    original = Path.resolve

    def extended(path, *args, **kwargs):
        resolved = original(path, *args, **kwargs)
        return Path("\\\\?\\" + str(resolved)) if path.name == "result.mp4" else resolved

    monkeypatch.setattr(Path, "resolve", extended)
    storage = CleanupStorage(root)
    assert storage.resolve("p", "outputs/result.mp4") == source
    with pytest.raises(ValueError):
        storage.resolve("p", "../outside.mp4")
    storage.delete_file("p", "outputs/result.mp4")
    assert not source.exists()
