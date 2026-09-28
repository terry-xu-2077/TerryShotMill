import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shotmill.app_factory import create_app
from shotmill.media.export_lease import SIGNATURE, export_lease
from test_batch_review_api import _project


def test_startup_recovers_crashed_export_but_keeps_other_live_download(client, providers):
    container = client.app.state.container
    project = _project(client)["id"]
    script = """
import os
import sys
from pathlib import Path
from shotmill.application.file_library import FileLibrary
from shotmill.application.project_export_service import ProjectExportService
from shotmill.media.file_storage import FileStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.repositories import SqlAlchemyUnitOfWork
engine = create_database_engine(sys.argv[1])
sessions = create_session_factory(engine)
service = ProjectExportService(lambda: SqlAlchemyUnitOfWork(sessions),
    FileLibrary(FileStorage(Path(sys.argv[2]))), Path(sys.argv[3]))
with service.prepare(sys.argv[4]) as package:
    print(str(package), flush=True)
    os._exit(71)
"""
    with container.project_export_service.prepare(project) as active:
        result = subprocess.run(
            [sys.executable, "-c", script, container.settings.database_url,
             str(container.settings.files_root), str(container.settings.projects_root), project],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            env={**os.environ, "PYTHONUTF8": "1"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert result.returncode == 71, result.stderr
        abandoned = Path(result.stdout.strip())
        assert abandoned.is_relative_to(container.settings.files_root / "staging")
        assert abandoned.is_file()
        app = create_app(
            container.settings, prompt_provider=providers[0], video_provider=providers[1],
        )
        with TestClient(app):
            assert not abandoned.parent.exists()
            assert active.is_file()
            assert active.read_bytes().startswith(b"PK")
        assert active.is_file()
    assert not active.parent.exists()


def test_recovery_preserves_unknown_or_extra_files_and_active_lease(client):
    container = client.app.state.container
    staging = container.settings.files_root / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    for suffix, marker, extra in (
        ("unknown1", b"not ShotMill", False),
        ("extra123", SIGNATURE, True),
        ("active12", SIGNATURE, False),
    ):
        directory = staging / f"project-export-{suffix}"
        directory.mkdir()
        (directory / "owner.lock").write_bytes(marker)
        (directory / "project.zip").write_bytes(b"retain")
        if extra:
            (directory / "user-note.txt").write_text("retain", encoding="utf-8")
    with export_lease(staging / "project-export-active12" / "owner.lock") as acquired:
        assert acquired
        assert container.project_export_service.recover_abandoned() == 0
    assert all((directory / "project.zip").read_bytes() == b"retain"
               for directory in staging.iterdir())


@pytest.mark.parametrize("blocked_name", ["project.zip", "owner.lock"])
def test_failed_export_cleanup_can_retry_without_removing_other_content(
    client, monkeypatch, blocked_name,
):
    service = client.app.state.container.project_export_service
    directory = service.library.storage.managed.resolve("staging", "project-export-retry123")
    directory.mkdir(parents=True)
    package = directory / "project.zip"
    package.write_bytes(b"partial zip")
    (directory / "owner.lock").write_bytes(SIGNATURE)
    neighbor = directory.parent / "user-export.zip"
    neighbor.write_bytes(b"user content")
    original = Path.unlink

    def fail_owned_file(path, *args, **kwargs):
        if path == directory / blocked_name:
            raise PermissionError("test file is in use")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_owned_file)
        assert service.recover_abandoned() == 0
    assert directory.is_dir()
    assert service.recover_abandoned() == 1
    assert not directory.exists()
    assert neighbor.read_bytes() == b"user content"
    assert service.recover_abandoned() == 0


@pytest.mark.parametrize("linked_name", ["project-export-link1234", "project.zip", "owner.lock"])
def test_export_recovery_rejects_link_detection_before_deleting(client, monkeypatch, linked_name):
    service = client.app.state.container.project_export_service
    directory = service.library.storage.managed.resolve("staging", "project-export-link1234")
    directory.mkdir(parents=True)
    (directory / "project.zip").write_bytes(b"retain")
    (directory / "owner.lock").write_bytes(SIGNATURE)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == linked_name or original(path))
    assert service.recover_abandoned() == 0
    assert (directory / "project.zip").read_bytes() == b"retain"
    assert (directory / "owner.lock").read_bytes() == SIGNATURE
