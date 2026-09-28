"""Abrupt child-process exits must not turn an incomplete archive into deletion."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from shotmill.application.lifecycle_service import LifecycleService
from shotmill.application.permanent_delete_service import PermanentDeleteService
from shotmill.application.result_archive_service import ResultArchiveService
from shotmill.media.archive_storage import ArchiveStorage
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from test_result_archive_service import archive  # noqa: F401

CHILD = r'''
import os
import sys
from pathlib import Path
from shotmill.application.permanent_delete_service import PermanentDeleteService
from shotmill.application.result_archive_service import ResultArchiveService
from shotmill.media.archive_storage import ArchiveStorage
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork

root = Path(sys.argv[1])
engine = create_database_engine(f"sqlite+pysqlite:///{(root / 'archive.db').as_posix()}")
sessions = create_session_factory(engine)
factory = lambda: SqlAlchemyUnitOfWork(sessions)
storage = ArchiveStorage(root / "archive")
service = ResultArchiveService(factory, MediaStorage(root / "projects"), storage)
if sys.argv[2] == "before_publish":
    # fsync is reached with the temporary output written, before publication.
    def crash(*args):
        os._exit(81)
    os.fsync = crash
else:
    original = storage.copy
    def crash(source):
        original(source)
        os._exit(82)
    storage.copy = crash
PermanentDeleteService(factory, service, CleanupStorage(root / "projects")).purge_tasks("p", ["t"])
raise AssertionError("Expected abrupt exit was not reached")
'''


@pytest.mark.parametrize("boundary,exit_code", [("before_publish", 81), ("after_publish", 82)])
def test_archive_process_exit_preserves_sources_and_retries_all_versions(
    archive, tmp_path, boundary, exit_code,  # noqa: F811
):
    service, factory = archive
    LifecycleService(factory).transition_tasks("p", ["t"], "trash")
    with factory() as uow:
        originals = {}
        for result in uow.results.list_by_task("t"):
            source = service._source("p", result.video_url)
            originals[source] = source.read_bytes()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "backend")
    child = subprocess.run(
        [sys.executable, "-c", CHILD, str(tmp_path), boundary],
        env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert child.returncode == exit_code, child.stderr
    # New engine and service simulate the next application process.
    engine = create_database_engine(f"sqlite+pysqlite:///{(tmp_path / 'archive.db').as_posix()}")
    sessions = create_session_factory(engine)

    def reopened():
        return SqlAlchemyUnitOfWork(sessions)

    resumed = ResultArchiveService(
        reopened, MediaStorage(tmp_path / "projects"), ArchiveStorage(tmp_path / "archive"),
    )
    try:
        with reopened() as uow:
            assert uow.tasks.get("t").deleted_at is not None
            assert len(uow.results.list_by_task("t")) == 2
            assert uow.cleanup.list() == []
        assert resumed.list() == []
        assert all(path.read_bytes() == content for path, content in originals.items())
        published = {
            path: path.stat().st_mtime_ns
            for path in (resumed.storage.root / "blobs").glob("*/*") if path.is_file()
        }
        assert len(published) == (0 if boundary == "before_publish" else 1)
        deletion = PermanentDeleteService(reopened, resumed, CleanupStorage(tmp_path / "projects"))
        assert deletion.purge_tasks("p", ["t"]).archived_result_count == 2
        records = resumed.list()
        assert len(records) == 2
        assert all(resumed.storage.verify(file) for record in records for file in record.files)
        assert all(path.stat().st_mtime_ns == modified for path, modified in published.items())
        assert deletion.cleanup_pending() == 1
        assert all(not path.exists() for path in originals)
        assert all(resumed.storage.verify(file) for record in records for file in record.files)
        with reopened() as uow:
            assert uow.tasks.get("t") is None
    finally:
        engine.dispose()
