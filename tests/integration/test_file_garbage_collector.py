import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from shotmill.application.file_garbage_collector import FileGarbageCollector
from shotmill.errors import ConflictError
from shotmill.persistence.repositories.files import SqlAlchemyFileRepository
from test_batch_review_api import _project, _task
from test_file_library import import_file, library  # noqa: F401
from test_prompt_batch_recovery import HeldQueue


def generated(client):
    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    project = _project(client)["id"]
    task = _task(client, project, "Output", "Generate")["id"]
    response = client.post(f"/api/v1/projects/{project}/tasks/{task}/generation", json={})
    assert response.status_code == 202
    client.portal.call(service.execute, response.json()["id"])
    with service.uow_factory() as uow:
        result = uow.results.list_by_task(task)[0]
    return container, project, task, result


def test_collection_preserves_shared_owners_and_unregistered_files(library):  # noqa: F811
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        orphan = import_file(service, uow)
        live = import_file(service, uow, owner="live", data=b"live")
        uow.files.release_owner("project", "p", "asset", "a")
    unknown = service.storage.managed.root / "keep.txt"
    unknown.write_text("unmanaged", encoding="utf-8")
    collector = FileGarbageCollector(factory, service.storage)
    assert collector.collect_registered() == 1
    assert collector.collect_registered() == 0
    assert not service.storage.resolve(orphan).exists()
    assert service.storage.resolve(live).read_bytes() == b"live"
    assert unknown.read_text(encoding="utf-8") == "unmanaged"
    with factory() as uow:
        assert uow.files.get(orphan.sha256) is None
        assert uow.files.get(live.sha256) == live


def test_active_generation_blocks_collection_before_inspecting_bytes():
    uow = Mock()
    uow.__enter__ = Mock(return_value=uow)
    uow.__exit__ = Mock(return_value=False)
    uow.jobs.list_active.return_value = [object()]
    storage = Mock()
    with pytest.raises(ConflictError, match="生成任务"):
        FileGarbageCollector(lambda: uow, storage).collect_registered()
    uow.reserve_write.assert_called_once()
    uow.files.unreferenced.assert_not_called()
    storage.resolve.assert_not_called()


def test_interrupted_registration_removal_retries_missing_bytes(library, monkeypatch):  # noqa: F811
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        orphan = import_file(service, uow)
        uow.files.release_owner("project", "p", "asset", "a")
    collector = FileGarbageCollector(factory, service.storage)
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyFileRepository, "delete_unreferenced",
                      Mock(side_effect=RuntimeError("injected database failure")))
        with pytest.raises(RuntimeError, match="injected"):
            collector.collect_registered()
    with factory() as uow:
        assert uow.files.get(orphan.sha256) == orphan
    assert not service.storage.resolve(orphan).exists()
    assert collector.collect_registered() == 1


@pytest.mark.parametrize("collect_first", [False, True])
def test_collection_and_import_serialize_on_database_write_lock(
    library, monkeypatch, collect_first,  # noqa: F811
):
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        file = import_file(service, uow)
        uow.files.release_owner("project", "p", "asset", "a")
    entered, release, started = Event(), Event(), Event()
    hook = "unreferenced" if collect_first else "register"
    original = getattr(SqlAlchemyFileRepository, hook)

    def hold(repository, *args):
        result = original(repository, *args)
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(SqlAlchemyFileRepository, hook, hold)
    collector = FileGarbageCollector(factory, service.storage)

    def importing():
        with factory() as uow:
            uow.reserve_write()
            return import_file(service, uow, project="destination", owner="new")

    def second_operation():
        started.set()
        return importing() if collect_first else collector.collect_registered()

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(collector.collect_registered if collect_first else importing)
        assert entered.wait(5)
        second = workers.submit(second_operation)
        try:
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.3)
        finally:
            release.set()
        first_value = first.result(timeout=5)
        second_value = second.result(timeout=5)
    assert (first_value if collect_first else second_value) == (1 if collect_first else 0)
    with factory() as uow:
        refs = uow.files.references(file.sha256)
        assert len(refs) == 1
        assert refs[0].scope_id == "destination"
        assert service.resolve(uow, refs[0]).read_bytes() == b"shared"


def test_changed_registered_bytes_are_not_deleted(library):  # noqa: F811
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        file = import_file(service, uow)
        uow.files.release_owner("project", "p", "asset", "a")
    path = service.storage.resolve(file)
    path.write_bytes(b"changed by external process")
    with pytest.raises(OSError, match="damaged"):
        FileGarbageCollector(factory, service.storage).collect_registered()
    assert path.read_bytes() == b"changed by external process"
    with factory() as uow:
        assert uow.files.get(file.sha256) == file


def test_real_generation_collection_window_blocks_reclaiming_reused_bytes(client, monkeypatch):
    container = client.app.state.container
    service = container.file_library
    factory = container.generation_service.uow_factory
    with factory() as uow:
        uow.reserve_write()
        file = import_file(service, uow, data=b"fake-video-bytes")
        uow.files.release_owner("project", "p", "asset", "a")
    collector = FileGarbageCollector(factory, service.storage)
    result_collector = container.generation_service.result_collector
    original = result_collector.collect
    inspected = []

    def inspect_before_publication(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result.files[0][0] == file
        with factory() as uow:
            assert uow.files.references(file.sha256) == []
            assert any(job.status == "running" for job in uow.jobs.list_active())
        with pytest.raises(ConflictError) as error:
            collector.collect_registered()
        assert error.value.code == "FILE_COLLECTION_BUSY"
        assert service.storage.resolve(file).read_bytes() == b"fake-video-bytes"
        inspected.append(result.result.id)
        return result

    monkeypatch.setattr(result_collector, "collect", inspect_before_publication)
    _, _, _, result = generated(client)
    assert inspected == [result.id]
    assert collector.collect_registered() == 0
    assert client.get(result.video_url).content == b"fake-video-bytes"


def test_process_exit_after_unlink_recovers_on_retry(library):  # noqa: F811
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        orphan = import_file(service, uow)
        live = import_file(service, uow, owner="live", data=b"keep")
        uow.files.release_owner("project", "p", "asset", "a")
        database = str(uow.session.get_bind().url)
    script = """
import os, sys
from shotmill.application.file_garbage_collector import FileGarbageCollector
from shotmill.media.file_storage import FileStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.repositories.files import SqlAlchemyFileRepository
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from pathlib import Path
engine = create_database_engine(sys.argv[1])
sessions = create_session_factory(engine)
def interrupt(self, sha256):
    os._exit(74)
SqlAlchemyFileRepository.delete_unreferenced = interrupt
FileGarbageCollector(lambda: SqlAlchemyUnitOfWork(sessions), FileStorage(Path(sys.argv[2]))
).collect_registered()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "backend")
    completed = subprocess.run(
        [sys.executable, "-c", script, database, str(service.storage.managed.root)],
        env=environment, capture_output=True, timeout=20,
    )
    assert completed.returncode == 74, completed.stderr.decode("utf-8", errors="replace")
    assert not service.storage.resolve(orphan).exists()
    with factory() as uow:
        assert uow.files.get(orphan.sha256) == orphan
        assert len(uow.files.references(live.sha256)) == 1
    assert FileGarbageCollector(factory, service.storage).collect_registered() == 1
    assert service.storage.resolve(live).read_bytes() == b"keep"
    with factory() as uow:
        assert uow.files.get(orphan.sha256) is None


@pytest.mark.parametrize("failure", ["linked-file", "linked-directory", "permission"])
def test_unsafe_or_locked_candidate_is_preserved_for_retry(library, monkeypatch, failure):  # noqa: F811
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        file = import_file(service, uow)
        uow.files.release_owner("project", "p", "asset", "a")
    path = service.storage.resolve(file)
    collector = FileGarbageCollector(factory, service.storage)
    with monkeypatch.context() as patch:
        if failure == "permission":
            original_unlink = Path.unlink

            def deny(candidate, *args, **kwargs):
                if candidate == path:
                    raise PermissionError("injected sharing violation")
                return original_unlink(candidate, *args, **kwargs)

            patch.setattr(Path, "unlink", deny)
            expected = PermissionError
        else:
            # Fault injection of link detection, not a Windows symlink setup test.
            original_link = Path.is_symlink
            target = path if failure == "linked-file" else path.parent
            patch.setattr(Path, "is_symlink", lambda candidate:
                          candidate == target or original_link(candidate))
            expected = ValueError
        with pytest.raises(expected):
            collector.collect_registered()
    assert path.read_bytes() == b"shared"
    with factory() as uow:
        assert uow.files.get(file.sha256) == file
    assert collector.collect_registered() == 1
