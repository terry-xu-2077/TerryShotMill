"""Versioned, verified transport container; domain validation belongs to the importer.

Never extract arbitrary ZIP paths. Only declared content-addressed blobs are written
into a private temporary directory, which is exposed after every checksum passes.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

CHUNK = 1024 * 1024
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class PackageLimits:
    max_entries: int = 20000
    max_manifest_bytes: int = 8 * 1024 * 1024
    max_file_bytes: int = 32 * 1024**3
    max_total_bytes: int = 64 * 1024**3


DEFAULT_LIMITS = PackageLimits()


@dataclass(frozen=True)
class StagedProjectPackage:
    records: dict
    files: dict[str, Path]


def _portable_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 1000:
        raise ValueError("Invalid package file path")
    if any(ord(c) < 32 or c in '\\:<>"|?*' for c in value):
        raise ValueError("Nonportable package file path")
    for part in value.split("/"):
        if part in {"", ".", ".."} or part.endswith((".", " ")) or RESERVED.match(part):
            raise ValueError("Nonportable package file path")
    return value


def _fingerprint(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _check_path_tree(paths: Mapping[str, object]) -> None:
    """A Windows destination cannot use the same name as a file and a directory."""
    names = {name.casefold() for name in paths}
    for name in names:
        parts = name.split("/")
        if any("/".join(parts[:index]) in names for index in range(1, len(parts))):
            raise ValueError("Package file/directory collision")


def write_project_package(
    target: BinaryIO, records: dict, files: Mapping[str, Path],
    *, limits: PackageLimits = DEFAULT_LIMITS,
) -> None:
    """Caller owns the unpublished output and ensures sources belong to the project."""
    if not isinstance(records, dict) or len(files) + 1 > limits.max_entries:
        raise ValueError("Invalid records or too many package entries")
    seen: set[str] = set()
    for name in files:
        _portable_path(name)
        if name.casefold() in seen:
            raise ValueError("Duplicate package file path")
        seen.add(name.casefold())
    _check_path_tree(files)
    manifest_files, blobs = [], {}
    for name, source in files.items():
        checksum, size = _fingerprint(source)
        if size > limits.max_file_bytes:
            raise ValueError("Package file size limit exceeded")
        manifest_files.append({"path": name, "sha256": checksum, "size": size})
        blobs.setdefault(checksum, (source, size))
    # Logical aliases share one physical object in the application-wide library.
    if sum(size for _, size in blobs.values()) > limits.max_total_bytes:
        raise ValueError("Package total size limit exceeded")
    manifest = json.dumps({
        "format": "shotmill-project", "version": 1, "records": records, "files": manifest_files,
    }, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(manifest) > limits.max_manifest_bytes:
        raise ValueError("Package manifest size limit exceeded")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr("manifest.json", manifest)
        for checksum, (source, expected_size) in blobs.items():
            digest, size = hashlib.sha256(), 0
            with source.open("rb") as incoming, archive.open(
                f"blobs/{checksum}", "w", force_zip64=True,
            ) as outgoing:
                while chunk := incoming.read(CHUNK):
                    size += len(chunk)
                    if size > expected_size:
                        raise ValueError("Source changed during export")
                    digest.update(chunk)
                    outgoing.write(chunk)
            if size != expected_size or digest.hexdigest() != checksum:
                raise ValueError("Source changed during export")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


@contextmanager
def open_project_package(
    source: BinaryIO, *, staging_parent: Path | None = None,
    limits: PackageLimits = DEFAULT_LIMITS,
) -> Iterator[StagedProjectPackage]:
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > limits.max_entries:
            raise ValueError("Too many package entries")
        names: set[str] = set()
        for info in entries:
            if info.filename.casefold() in names:
                raise ValueError("Duplicate ZIP member")
            names.add(info.filename.casefold())
            if info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Encrypted or symlink ZIP member")
            if info.filename != "manifest.json" and not re.fullmatch(
                r"blobs/[0-9a-f]{64}", info.filename,
            ):
                raise ValueError("Unexpected ZIP member")
        if "manifest.json" not in archive.namelist():
            raise ValueError("Missing project manifest")
        if archive.getinfo("manifest.json").file_size > limits.max_manifest_bytes:
            raise ValueError("Package manifest size limit exceeded")
        manifest = json.loads(
            archive.read("manifest.json"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if (not isinstance(manifest, dict) or manifest.get("format") != "shotmill-project"
                or type(manifest.get("version")) is not int or manifest["version"] != 1
                or not isinstance(manifest.get("records"), dict)
                or not isinstance(manifest.get("files"), list)):
            raise ValueError("Unsupported project package manifest")
        if len(manifest["files"]) + 1 > limits.max_entries:
            raise ValueError("Too many package files")
        paths: dict[str, str] = {}
        sizes: dict[str, int] = {}
        logical_names: set[str] = set()
        for file in manifest["files"]:
            if not isinstance(file, dict):
                raise ValueError("Invalid file declaration")
            path = _portable_path(file.get("path"))
            checksum, size = file.get("sha256"), file.get("size")
            if (not isinstance(checksum, str) or not SHA256.fullmatch(checksum)
                    or type(size) is not int or size < 0):
                raise ValueError("Invalid file checksum or size")
            if path.casefold() in logical_names or sizes.get(checksum, size) != size:
                raise ValueError("Conflicting file declaration")
            if size > limits.max_file_bytes:
                raise ValueError("Package file size limit exceeded")
            logical_names.add(path.casefold())
            paths[path], sizes[checksum] = checksum, size
        _check_path_tree(paths)
        if sum(sizes.values()) > limits.max_total_bytes:
            raise ValueError("Package total size limit exceeded")
        expected = {"manifest.json", *(f"blobs/{checksum}" for checksum in sizes)}
        if set(archive.namelist()) != expected:
            raise ValueError("Missing or unreferenced package content")
        for checksum, size in sizes.items():
            if archive.getinfo(f"blobs/{checksum}").file_size != size:
                raise ValueError("Declared file size mismatch")
        with tempfile.TemporaryDirectory(
            prefix="shotmill-import-", dir=staging_parent,
        ) as directory:
            root = Path(directory)
            for checksum, expected_size in sizes.items():
                digest, size = hashlib.sha256(), 0
                with (
                    archive.open(f"blobs/{checksum}") as incoming,
                    (root / checksum).open("xb") as out,
                ):
                    while chunk := incoming.read(CHUNK):
                        size += len(chunk)
                        if size > expected_size:
                            raise ValueError("Expanded file size limit exceeded")
                        digest.update(chunk)
                        out.write(chunk)
                if size != expected_size or digest.hexdigest() != checksum:
                    raise ValueError("Package file checksum mismatch")
            yield StagedProjectPackage(manifest["records"], {
                name: root / checksum for name, checksum in paths.items()
            })
