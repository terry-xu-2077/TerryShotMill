import io
import json
import stat
import zipfile

import pytest
from shotmill.media.project_package import (
    PackageLimits,
    open_project_package,
    write_project_package,
)


def test_roundtrip_deduplicates_bytes_and_removes_private_staging(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"video" * 300000)
    package = io.BytesIO()
    write_project_package(package, {"title": "迁移项目"}, {
        "assets/reference.mp4": source, "outputs/history.mp4": source,
    })
    with zipfile.ZipFile(package) as archive:
        assert len(archive.namelist()) == 2
    with open_project_package(package, staging_parent=tmp_path) as staged:
        assert staged.records == {"title": "迁移项目"}
        assert staged.files["assets/reference.mp4"].read_bytes() == source.read_bytes()
        assert staged.files["outputs/history.mp4"] == staged.files["assets/reference.mp4"]
        path = staged.files["outputs/history.mp4"]
    assert not path.exists()
    assert source.exists()


@pytest.mark.parametrize("path", [
    "../outside", "/absolute", "C:/outside", "assets\\outside", "assets/../outside",
    "assets/CON.txt", "assets/file.", "assets/file ", "assets/a:stream", "assets//file",
])
def test_export_rejects_nonportable_paths_before_writing(tmp_path, path):
    source = tmp_path / "source"
    source.write_bytes(b"x")
    output = io.BytesIO()
    with pytest.raises(ValueError):
        write_project_package(output, {}, {path: source})
    assert output.getvalue() == b""


def archive_with(manifest, entries=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in entries:
            archive.writestr(name, content)
    return buffer


def test_import_rejects_unknown_version_extra_members_and_case_collisions(tmp_path):
    base = {"format": "shotmill-project", "version": 1, "records": {}, "files": []}
    packages = [
        archive_with({**base, "version": 2}),
        archive_with(base, [("../outside", b"x")]),
        archive_with(base, [("MANIFEST.JSON", b"{}")]),
    ]
    for package in packages:
        with pytest.raises(ValueError):
            with open_project_package(package, staging_parent=tmp_path):
                pytest.fail("must not publish invalid package")
    assert list(tmp_path.iterdir()) == []


def test_corrupt_content_is_rejected_without_leaking_staging(tmp_path):
    digest = "0" * 64
    manifest = {"format": "shotmill-project", "version": 1, "records": {}, "files": [
        {"path": "assets/test.txt", "sha256": digest, "size": 3},
    ]}
    package = archive_with(manifest, [(f"blobs/{digest}", b"bad")])
    with pytest.raises(ValueError, match="checksum"):
        with open_project_package(package, staging_parent=tmp_path):
            pytest.fail("must verify all files before exposing records")
    assert list(tmp_path.iterdir()) == []


def test_capacity_limit_is_checked_before_extraction(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"1234")
    package = io.BytesIO()
    write_project_package(package, {}, {"assets/a": source})
    with pytest.raises(ValueError, match="size limit"):
        with open_project_package(package, limits=PackageLimits(max_file_bytes=3)):
            pytest.fail("must reject oversized media")


def test_export_rejects_case_insensitive_path_collision(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"x")
    with pytest.raises(ValueError):
        write_project_package(io.BytesIO(), {}, {"assets/A.png": source, "assets/a.png": source})


def test_export_detects_source_changed_between_hash_and_copy(tmp_path, monkeypatch):
    from shotmill.media import project_package

    source = tmp_path / "source"
    source.write_bytes(b"old")
    original = project_package._fingerprint

    def changed(path):
        result = original(path)
        path.write_bytes(b"new")
        return result

    monkeypatch.setattr(project_package, "_fingerprint", changed)
    with pytest.raises(ValueError, match="Source changed"):
        write_project_package(io.BytesIO(), {}, {"assets/a": source})


@pytest.mark.parametrize("raw", [
    b'{"format":"shotmill-project","version":1,"version":1,"records":{},"files":[]}',
    b'{"format":"shotmill-project","version":true,"records":{},"files":[]}',
    b'{"format":"shotmill-project","version":1,"records":{"value":NaN},"files":[]}',
])
def test_import_rejects_ambiguous_json(raw):
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", raw)
    with pytest.raises(ValueError):
        with open_project_package(package):
            pytest.fail("must not accept ambiguous manifest")


def test_import_rejects_symlink_even_with_blob_shaped_name():
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        link = zipfile.ZipInfo("blobs/" + "0" * 64)
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../outside")
    with pytest.raises(ValueError, match="symlink"):
        with open_project_package(package):
            pytest.fail("must not materialize links")


def test_consumer_failure_cleans_verified_staging_but_preserves_archive(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"source")
    package = io.BytesIO()
    write_project_package(package, {}, {"assets/a": source})
    with pytest.raises(RuntimeError, match="database failed"):
        with open_project_package(package, staging_parent=tmp_path) as staged:
            staged_path = staged.files["assets/a"]
            raise RuntimeError("database failed")
    assert not staged_path.exists()
    with open_project_package(package, staging_parent=tmp_path) as retry:
        assert retry.files["assets/a"].read_bytes() == b"source"


@pytest.mark.parametrize("paths", [
    ["assets/a", "assets/a/frame.png"],
    ["assets/A/frame.png", "assets/a"],
])
def test_export_rejects_file_directory_collision_before_writing(tmp_path, paths):
    source = tmp_path / "source"
    source.write_bytes(b"1234")
    package = io.BytesIO()
    with pytest.raises(ValueError, match="collision"):
        write_project_package(package, {}, dict.fromkeys(paths, source))
    assert package.getvalue() == b""


def test_import_rejects_file_directory_collision_before_staging(tmp_path):
    import hashlib

    digest = hashlib.sha256(b"1234").hexdigest()
    manifest = {"format": "shotmill-project", "version": 1, "records": {}, "files": [
        {"path": name, "sha256": digest, "size": 4}
        for name in ["assets/A/frame.png", "assets/a"]
    ]}
    package = archive_with(manifest, [(f"blobs/{digest}", b"1234")])
    with pytest.raises(ValueError, match="collision"):
        with open_project_package(package, staging_parent=tmp_path):
            pytest.fail("cannot publish colliding files")
    assert list(tmp_path.iterdir()) == []


def test_export_capacity_counts_shared_objects_once(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"1234")
    package = io.BytesIO()
    write_project_package(package, {}, {
        "assets/a": source, "assets/b": source,
    }, limits=PackageLimits(max_total_bytes=4))
    with zipfile.ZipFile(package) as archive:
        assert len(archive.namelist()) == 2
    with pytest.raises(ValueError, match="total size"):
        write_project_package(io.BytesIO(), {}, {"assets/a": source},
                              limits=PackageLimits(max_total_bytes=3))


def test_import_capacity_counts_shared_objects_once_and_limits_references(tmp_path):
    import hashlib

    digest = hashlib.sha256(b"1234").hexdigest()
    manifest = {"format": "shotmill-project", "version": 1, "records": {}, "files": [
        {"path": name, "sha256": digest, "size": 4} for name in ["assets/a", "assets/b"]
    ]}
    package = archive_with(manifest, [(f"blobs/{digest}", b"1234")])
    with open_project_package(
        package, staging_parent=tmp_path, limits=PackageLimits(max_total_bytes=4),
    ) as staged:
        assert staged.files["assets/a"] == staged.files["assets/b"]
    with pytest.raises(ValueError, match="Too many package files"):
        with open_project_package(
            package, staging_parent=tmp_path, limits=PackageLimits(max_entries=2),
        ):
            pytest.fail("logical references must still have a count limit")
    assert list(tmp_path.iterdir()) == []
