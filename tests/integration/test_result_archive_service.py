import pytest
from shotmill.application.lifecycle_service import LifecycleService
from shotmill.application.permanent_delete_service import PermanentDeleteService
from shotmill.application.result_archive_service import ResultArchiveService
from shotmill.domain.entities import ContextLink, Job, Project, Result, Task
from shotmill.domain.enums import JobStatus
from shotmill.errors import ShotMillError
from shotmill.media.archive_storage import ArchiveStorage
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.migrations import upgrade_database
from shotmill.persistence.repositories.archive import SqlAlchemyArchivedResultRepository
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork


@pytest.fixture
def archive(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'archive.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)

    def factory():
        return SqlAlchemyUnitOfWork(sessions)

    media = MediaStorage(tmp_path / "projects")
    service = ResultArchiveService(factory, media, ArchiveStorage(tmp_path / "archive"))
    with factory() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        uow.tasks.add(Task(id="t", project_id="p", title="Task", display_order=1))
        for index in range(2):
            job_id = f"job{index}"
            uow.jobs.add(Job(
                id=job_id, project_id="p", task_id="t", status=JobStatus.COMPLETED,
                final_prompt_snapshot=f"submitted prompt {index}", task_content_snapshot={},
                assets_snapshot=[], generation_profile_snapshot={},
                provider_profile_snapshot={"api_key": "do not archive credentials"},
                params_snapshot={"seed": index}, context_snapshot={},
            ))
            relative = media.write_output("p", job_id, "video.mp4", f"video{index}".encode())
            uow.results.add(Result(
                id=f"r{index}", project_id="p", task_id="t", job_id=job_id,
                video_url=media.media_url("p", relative), metadata={"duration": index + 1},
            ))
    yield service, factory
    engine.dispose()


def test_archives_all_versions_from_job_snapshots_and_is_idempotent(archive):
    service, factory = archive
    records = service.archive_tasks("p", ["t", "t"])
    assert len(records) == 2
    assert {r.final_prompt for r in records} == {"submitted prompt 0", "submitted prompt 1"}
    assert {r.params["seed"] for r in records} == {0, 1}
    assert all(service.storage.verify(r.files[0]) for r in records)
    assert {r.id for r in service.archive_tasks("p", ["t"])} == {r.id for r in records}
    assert "api_key" not in repr(records)
    with factory() as uow:
        assert len(uow.results.list_by_task("t")) == 2
    assert len(service.list("p")) == 2


def test_task_purge_archives_every_version_without_repairing_downstream(archive):
    service, factory = archive
    with factory() as uow:
        originals = {result.id: result for result in uow.results.list_by_task("t")}
        uow.tasks.add(Task(id="downstream", project_id="p", title="Next", display_order=2))
        uow.contexts.replace_for_target("downstream", [
            ContextLink("link", "p", "t", "downstream", "visual", "r0"),
        ])
    LifecycleService(factory).transition_tasks("p", ["t"], "trash")
    deletion = PermanentDeleteService(factory, service, CleanupStorage(service.media.projects_root))
    assert deletion.purge_tasks("p", ["t"]).archived_result_count == 2
    assert deletion.cleanup_pending() == 1
    records = service.list("p")
    assert {record.source_result_id for record in records} == {"r0", "r1"}
    for record in records:
        assert record.generated_at == originals[record.source_result_id].created_at
        assert record.source_project_title == "Project"
        assert record.source_task_title == "Task"
        assert service.storage.verify(record.files[0])
    with factory() as uow:
        assert uow.tasks.get("t") is None
        link = uow.contexts.list_by_target("downstream")[0]
        assert link.source_task_id == "t"
        assert link.source_result_id == "r0"
        assert link.source_deleted_at is not None
    for original in originals.values():
        assert not service._source("p", original.video_url).exists()


def test_failure_does_not_publish_partial_archive_or_remove_sources(archive, monkeypatch):
    service, factory = archive
    original_copy = service.storage.copy
    calls = 0

    def fail_second(source):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return original_copy(source)

    monkeypatch.setattr(service.storage, "copy", fail_second)
    with pytest.raises(ShotMillError) as failure:
        service.archive_tasks("p", ["t"])
    assert failure.value.code == "RESULT_ARCHIVE_FAILED"
    assert service.list() == []
    with factory() as uow:
        results = uow.results.list_by_task("t")
        assert len(results) == 2
        assert all(service._source("p", result.video_url).is_file() for result in results)
    monkeypatch.setattr(service.storage, "copy", original_copy)
    assert len(service.archive_tasks("p", ["t"])) == 2


def test_damaged_existing_archive_blocks_success(archive):
    service, _ = archive
    record = service.archive_tasks("p", ["t"])[0]
    service.storage.resolve(record.files[0]["path"]).unlink()
    with pytest.raises(ShotMillError) as failure:
        service.archive_tasks("p", ["t"])
    assert failure.value.code == "ARCHIVE_DAMAGED"


def test_database_failure_keeps_copies_for_verified_retry_without_sweeping_unknown_files(
    archive, monkeypatch,
):
    service, factory = archive
    original = SqlAlchemyArchivedResultRepository.add
    calls = 0

    def fail_second(self, record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("database write failed")
        return original(self, record)

    monkeypatch.setattr(SqlAlchemyArchivedResultRepository, "add", fail_second)
    with pytest.raises(RuntimeError, match="database write failed"):
        service.archive_tasks("p", ["t"])
    assert service.list() == []
    published = {path: path.stat().st_mtime_ns
                 for path in (service.storage.root / "blobs").glob("*/*") if path.is_file()}
    assert len(published) == 2
    unrelated = service.storage.root / "keep.txt"
    unrelated.write_text("user file", encoding="utf-8")
    cleanup = PermanentDeleteService(factory, service, CleanupStorage(service.media.projects_root))
    assert cleanup.cleanup_pending() == 0
    assert all(path.exists() for path in published)
    assert unrelated.read_text(encoding="utf-8") == "user file"
    with factory() as uow:
        assert all(service._source("p", result.video_url).is_file()
                   for result in uow.results.list_by_task("t"))
    monkeypatch.setattr(SqlAlchemyArchivedResultRepository, "add", original)
    records = service.archive_tasks("p", ["t"])
    assert len(records) == 2
    assert {service.storage.resolve(file["path"]) for record in records
            for file in record.files} == set(published)
    assert all(path.stat().st_mtime_ns == modified for path, modified in published.items())
    assert all(service.storage.verify(file) for record in records for file in record.files)


@pytest.mark.parametrize("url", [
    "https://example.com/video.mp4", "/media/other/outputs/video.mp4",
    "/media/p/%2e%2e/outside.mp4", "/media/p/C:/outside.mp4",
])
def test_archive_rejects_external_and_escaping_paths(archive, url):
    service, _ = archive
    with pytest.raises(ValueError):
        service._source("p", url)


def test_archive_api_lists_previews_downloads_and_missing_files(archive, client):
    service, _ = archive
    client.app.state.container.result_archive_service = service
    records = service.archive_tasks("p", ["t"])
    response = client.get("/api/v1/result-archive?sourceProjectId=p")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["sourceProjectTitle"] == "Project"
    assert "path" not in items[0]["files"][0]
    url = items[0]["files"][0]["url"]
    preview = client.get(url)
    assert preview.status_code == 200
    assert preview.content in (b"video0", b"video1")
    assert preview.headers["content-type"].startswith("video/mp4")
    assert preview.headers["content-disposition"].startswith("inline")
    download = client.get(url + "?download=true")
    assert download.headers["content-disposition"].startswith("attachment")
    assert client.get("/api/v1/result-archive?sourceProjectId=other").json() == []
    assert client.get("/api/v1/result-archive/missing/files/0").status_code == 404
    assert client.get(f"/api/v1/result-archive/{records[0].id}/files/-1").status_code == 404
    service.storage.resolve(records[0].files[0]["path"]).unlink()
    assert client.get(f"/api/v1/result-archive/{records[0].id}/files/0").status_code == 409
