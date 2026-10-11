"""Find only the media named by a project document and bind package paths."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit

from shotmill.application.file_library import FileLibrary
from shotmill.domain.files import StoredFile
from shotmill.media.project_package import _portable_path
from shotmill.media.storage import MediaStorage
from shotmill.persistence.project_documents import ProjectDocumentStore


def media_paths(document: dict) -> set[str]:
    project_id = document["projectId"]
    prefix = f"/media/{project_id}/"
    paths = {row["logical_path"] for row in document["tables"]["project_file_paths"]}
    for asset in document["tables"]["assets"]:
        paths.add(asset["project_relative_path"])
        if asset["thumbnail_path"]:
            paths.add(asset["thumbnail_path"])

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "projectRelativePath" and isinstance(item, str):
                    paths.add(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str) and value.startswith(prefix):
            parsed = urlsplit(value)
            if parsed.path.startswith(prefix) and not parsed.scheme and not parsed.netloc:
                paths.add(unquote(parsed.path[len(prefix):]))

    for rows in document["tables"].values():
        visit(rows)
    for path in paths:
        _portable_path(path)
    return paths


def collect_package_files(
    document: dict, documents: ProjectDocumentStore, media: MediaStorage,
    library: FileLibrary,
) -> tuple[dict, dict[str, Path]]:
    project_id = document["projectId"]
    rows = document["tables"]
    path_map = {row["logical_path"]: row["source_path"]
                for row in rows["project_file_paths"]}
    references = {
        f"shared/{row['owner_kind']}/{row['owner_id']}/{row['slot']}": row["sha256"]
        for row in rows["file_references"]
        if row["scope_kind"] == "project" and row["scope_id"] == project_id
    }
    stored = {row["sha256"]: row for row in rows["stored_files"]}
    files = {}
    for relative in media_paths(document):
        if relative in path_map:
            source = documents.resolve_reference(project_id, path_map[relative])
        elif relative.startswith("shared/"):
            checksum = references.get(relative)
            if checksum is None or checksum not in stored:
                raise ValueError(f"项目媒体引用缺失：{relative}")
            entry = stored[checksum]
            source = library.storage.resolve(StoredFile(
                checksum, entry["size"], entry["storage_path"],
            ))
        else:
            source = media.resolve(project_id, relative)
        if not source.is_file():
            raise ValueError(f"项目媒体文件缺失：{relative}")
        files[f"project.files/{relative}"] = source
    for checksum, row in stored.items():
        source = library.storage.resolve(StoredFile(
            checksum, row["size"], row["storage_path"],
        ))
        if not source.is_file():
            raise ValueError(f"项目共享文件缺失：{checksum}")
        files[f"library/{checksum}"] = source

    portable = deepcopy(document)
    for row in portable["tables"]["project_file_paths"]:
        row["source_path"] = f"project.files/{row['logical_path']}"
    return portable, files


def bind_imported_paths(document: dict, file_stem: str) -> dict:
    result = deepcopy(document)
    for row in result["tables"]["project_file_paths"]:
        expected = f"project.files/{row['logical_path']}"
        if row["source_path"] != expected:
            raise ValueError("项目包包含未收集的外部文件引用")
        row["source_path"] = f"{file_stem}.files/{row['logical_path']}"
    return result
