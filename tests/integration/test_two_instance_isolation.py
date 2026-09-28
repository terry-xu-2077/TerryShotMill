"""Real HTTP processes, not two project records sharing one application container."""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
from shotmill.application.asset_service import AssetService
from shotmill.domain.entities import Project
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.migrations import upgrade_database
from shotmill.persistence.repositories import SqlAlchemyUnitOfWork
from test_batch_review_api import _task

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def independent_server(data_root, *, provider_environment=None):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {
        **os.environ,
        **(provider_environment or {}),
        "SHOTMILL_DATA_ROOT": str(data_root),
        "SHOTMILL_DATABASE_URL": f"sqlite+pysqlite:///{(data_root / 'shotmill.db').as_posix()}",
        "SHOTMILL_AUTO_MIGRATE": "true",
        "PYTHONIOENCODING": "utf-8",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "shotmill.app:app", "--app-dir", "backend",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False,
        ) as client:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise AssertionError(f"Test server exited: {process.returncode}")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() >= deadline:
                    raise AssertionError("Test server did not become healthy")
                time.sleep(0.1)
            yield client, process.pid
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_two_http_instances_have_independent_databases_and_file_libraries(tmp_path):
    left_root, right_root = tmp_path / "left", tmp_path / "right"
    with independent_server(left_root) as (left, left_pid), independent_server(right_root) as (
        right, right_pid,
    ):
        assert left_pid != right_pid
        assert left.base_url != right.base_url
        left_project = left.post("/api/v1/projects", json={"title": "Left"}).json()["id"]
        right_project = right.post("/api/v1/projects", json={"title": "Right"}).json()["id"]
        assert right.get(f"/api/v1/projects/{left_project}/workspace").status_code == 404
        assert left.get(f"/api/v1/projects/{right_project}/workspace").status_code == 404
        urls = {}
        for client, project, root in (
            (left, left_project, left_root), (right, right_project, right_root),
        ):
            response = client.post(
                f"/api/v1/projects/{project}/assets",
                files={"file": ("sample.png", b"same-content", "image/png")},
            )
            assert response.status_code == 201, response.text
            asset = response.json()
            url = f"/media/{project}/{asset['projectRelativePath']}"
            urls[project] = url
            assert client.get(url).content == b"same-content"
            assert root.joinpath("shotmill.db").is_file()
        left_files = list((left_root / "files" / "objects").glob("*/*"))
        right_files = list((right_root / "files" / "objects").glob("*/*"))
        assert len(left_files) == len(right_files) == 1
        assert left_files[0].name == right_files[0].name
        assert not left_files[0].samefile(right_files[0])
        # Failure injection affects only this test's owned left instance file.
        left_files[0].unlink()
        assert left.get(urls[left_project]).status_code == 404
        assert right.get(urls[right_project]).content == b"same-content"


def test_two_process_project_zip_roundtrip_survives_source_deletion(tmp_path):
    with independent_server(tmp_path / "left") as (left, _), independent_server(
        tmp_path / "right",
    ) as (right, _):
        original = left.post("/api/v1/projects", json={"title": "Portable"}).json()["id"]
        _task(left, original, "Portable task", "Original prompt")
        uploaded = left.post(f"/api/v1/projects/{original}/assets", files={
            "file": ("sample.png", b"portable-content", "image/png"),
        })
        assert uploaded.status_code == 201, uploaded.text
        exported = left.get(f"/api/v1/projects/{original}/export")
        assert exported.status_code == 200, exported.text
        imported = right.post("/api/v1/projects/import", files={
            "file": ("project.zip", exported.content, "application/zip"),
        })
        assert imported.status_code == 201, imported.text
        destination = imported.json()["projectId"]
        assert destination != original
        workspace = right.get(f"/api/v1/projects/{destination}/workspace")
        assert workspace.status_code == 200 and "Portable task" in workspace.text
        exported_back = right.get(f"/api/v1/projects/{destination}/export")
        assert exported_back.status_code == 200, exported_back.text
        back = left.post("/api/v1/projects/import", files={
            "file": ("project.zip", exported_back.content, "application/zip"),
        })
        assert back.status_code == 201, back.text
        returned = back.json()["projectId"]
        assert len({original, destination, returned}) == 3
        assert left.post(f"/api/v1/projects/{original}/lifecycle", json={
            "action": "trash",
        }).status_code == 200
        purged = left.post(
            f"/api/v1/projects/{original}/permanent-delete", json={"confirmed": True},
        )
        assert purged.status_code == 200, purged.text
        for client, project in ((right, destination), (left, returned)):
            assets = client.get(f"/api/v1/projects/{project}/assets").json()["items"]
            assert len(assets) == 1
            url = f"/media/{project}/{assets[0]['projectRelativePath']}"
            assert client.get(url).content == b"portable-content"
        assert len(list((tmp_path / "left" / "files" / "objects").glob("*/*"))) == 1
        assert len(list((tmp_path / "right" / "files" / "objects").glob("*/*"))) == 1


def test_migrated_old_project_exports_to_independent_instance_without_legacy_files(tmp_path):
    left_root = tmp_path / "left"
    media = MediaStorage(left_root / "projects")
    database_url = f"sqlite+pysqlite:///{(left_root / 'shotmill.db').as_posix()}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    try:
        sessions = create_session_factory(engine)

        def factory():
            return SqlAlchemyUnitOfWork(sessions)

        with factory() as uow:
            uow.projects.add(Project(id="old-project", title="Legacy migration"))
        asset = AssetService(factory, media).import_bytes(
            "old-project", "original.png", b"legacy-portable-content",
        )
    finally:
        engine.dispose()
    migration = subprocess.run(
        [sys.executable, "-m", "shotmill.migrate_legacy_files", "--data-root", str(left_root),
         "--project", "old-project", "--apply"],
        cwd=ROOT, capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert migration.returncode == 0, migration.stderr
    # Only the temporary fixture's old copy is removed; both servers start fresh.
    media.resolve("old-project", asset.project_relative_path).unlink()
    with independent_server(left_root) as (left, left_pid), independent_server(
        tmp_path / "right",
    ) as (right, right_pid):
        assert left_pid != right_pid
        assert left.get(media.media_url("old-project", asset.project_relative_path)).content == (
            b"legacy-portable-content"
        )
        exported = left.get("/api/v1/projects/old-project/export")
        assert exported.status_code == 200, exported.text
        imported = right.post("/api/v1/projects/import", files={
            "file": ("legacy.zip", exported.content, "application/zip"),
        })
        assert imported.status_code == 201, imported.text
        destination = imported.json()["projectId"]
        assert destination != "old-project"
        assert left.post("/api/v1/projects/old-project/lifecycle", json={
            "action": "trash",
        }).status_code == 200
        purged = left.post("/api/v1/projects/old-project/permanent-delete", json={
            "confirmed": True,
        })
        assert purged.status_code == 200, purged.text
        assets = right.get(f"/api/v1/projects/{destination}/assets").json()["items"]
        assert len(assets) == 1
        assert assets[0]["originalFileName"] == "original.png"
        destination_url = media.media_url(destination, assets[0]["projectRelativePath"])
        assert right.get(destination_url).content == b"legacy-portable-content"
