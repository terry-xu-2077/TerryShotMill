import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from shotmill.app_factory import create_app
from shotmill.application.asset_service import AssetService
from shotmill.config import Settings
from shotmill.desktop_lock import desktop_data_lock
from shotmill.media.legacy_paths import legacy_owner_id
from test_batch_review_api import _project


@pytest.fixture
def client(tmp_path, providers):
    root = tmp_path / "data"
    settings = Settings(
        app_name="ShotMill", api_version="0.3", data_root=root,
        database_url=f"sqlite+pysqlite:///{(root / 'shotmill.db').as_posix()}",
    )
    app = create_app(settings, prompt_provider=providers[0], video_provider=providers[1])
    with TestClient(app) as test_client:
        yield test_client


def invoke(root, project, *extra):
    return subprocess.run(
        [sys.executable, "-m", "shotmill.migrate_legacy_files", "--data-root", str(root),
         "--project", project, *extra],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def test_explicit_migration_process_and_restart_preserve_old_files(client):
    container = client.app.state.container
    project = _project(client)["id"]
    asset = AssetService(container.generation_service.uow_factory, container.storage).import_bytes(
        project, "legacy.png", b"legacy",
    )
    root = container.settings.data_root
    assert invoke(root, project).returncode != 0
    for _ in range(2):
        result = invoke(root, project, "--apply")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "projectId": project, "mappedPaths": 1, "legacyFilesRemoved": 0,
        }
        assert container.storage.resolve(project, asset.project_relative_path).read_bytes() == (
            b"legacy"
        )
        resolved = container.storage.resolve_read(project, asset.project_relative_path)
        assert resolved.is_relative_to(container.settings.files_root)
        assert resolved.read_bytes() == b"legacy"
    with desktop_data_lock(root):
        assert invoke(root, project, "--apply").returncode != 0


def test_migration_does_not_create_an_unknown_data_directory(tmp_path):
    root = tmp_path / "missing"
    assert invoke(root, "project", "--apply").returncode != 0
    assert not root.exists()


def test_abrupt_migration_exit_rolls_back_mapping_and_retry_reuses_complete_blob(client):
    container = client.app.state.container
    factory = container.generation_service.uow_factory
    project = _project(client)["id"]
    asset = AssetService(factory, container.storage).import_bytes(
        project, "legacy.png", b"original bytes",
    )
    script = """
import os
import sys
from pathlib import Path
from shotmill.application.file_library import FileLibrary
from shotmill.migrate_legacy_files import migrate
original = FileLibrary.import_path
def interrupted(self, *args, **kwargs):
    original(self, *args, **kwargs)
    os._exit(73)
FileLibrary.import_path = interrupted
migrate(Path(sys.argv[1]), [sys.argv[2]])
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(container.settings.data_root), project],
        capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 73, result.stderr
    blobs = list(container.settings.files_root.glob("objects/*/*"))
    assert len(blobs) == 1
    assert blobs[0].read_bytes() == b"original bytes"
    with factory() as uow:
        assert uow.files.get(asset.hash) is None
        assert uow.files.get_reference(
            "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
            "content",
        ) is None
    old = container.storage.resolve(project, asset.project_relative_path)
    assert old.read_bytes() == b"original bytes"
    retried = invoke(container.settings.data_root, project, "--apply")
    assert retried.returncode == 0, retried.stderr
    assert json.loads(retried.stdout)["mappedPaths"] == 1
    assert list(container.settings.files_root.glob("objects/*/*")) == blobs
    assert container.storage.resolve_read(project, asset.project_relative_path) == blobs[0]
    assert old.read_bytes() == b"original bytes"
