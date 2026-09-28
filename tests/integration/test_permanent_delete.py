from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest
from shotmill.application.asset_service import AssetService
from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationService
from shotmill.application.lifecycle_service import LifecycleService
from shotmill.application.permanent_delete_service import PermanentDeleteService
from shotmill.application.result_archive_service import ResultArchiveService
from shotmill.domain.entities import (
    ContextLink,
    Job,
    Project,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Result,
    Task,
)
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError, ShotMillError
from shotmill.media.archive_storage import ArchiveStorage
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.migrations import upgrade_database
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork


@pytest.fixture
def output_paths():
    return {}


@pytest.fixture(params=["legacy", "content-addressed"])
def deletion(tmp_path, output_paths, request):
    url = f"sqlite+pysqlite:///{(tmp_path / 'delete.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)

    def factory():
        return SqlAlchemyUnitOfWork(sessions)

    media = MediaStorage(tmp_path / "projects")
    archive = ResultArchiveService(factory, media, ArchiveStorage(tmp_path / "archive"))
    service = PermanentDeleteService(factory, archive, CleanupStorage(media.projects_root))
    with factory() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        for index, name in enumerate(["source", "target"]):
            uow.tasks.add(Task(id=name, project_id="p", title=name, display_order=index + 1))
            uow.jobs.add(Job(
                id=f"job-{name}", project_id="p", task_id=name, status=JobStatus.COMPLETED,
                final_prompt_snapshot="prompt", task_content_snapshot={}, assets_snapshot=[],
                generation_profile_snapshot={}, provider_profile_snapshot={},
                params_snapshot={"seed": index}, context_snapshot={},
            ))
            if request.param == "legacy":
                path = f"outputs/job-{name}/video.mp4"
                destination = media.resolve("p", path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(name.encode())
            else:
                path = media.write_output("p", f"job-{name}", "video.mp4", name.encode())
            output_paths[name] = path
            uow.results.add(Result(
                id=f"result-{name}", project_id="p", task_id=name, job_id=f"job-{name}",
                video_url=media.media_url("p", path),
            ))
        uow.contexts.replace_for_target("target", [
            ContextLink("link", "p", "source", "target", "visual", "result-source")
        ])
    yield service, LifecycleService(factory), factory
    engine.dispose()


def test_task_purge_archives_and_preserves_missing_reference(deletion, output_paths):
    service, lifecycle, factory = deletion
    lifecycle.transition_tasks("p", ["source"], "trash")
    outcome = service.purge_tasks("p", ["source"])
    assert outcome.archived_result_count == 1
    with factory() as uow:
        assert uow.tasks.get("source") is None
        assert uow.results.get("result-source") is None
        assert uow.jobs.get("job-source") is None
        assert uow.contexts.list_by_target("target")[0].source_task_title == "source"
        assert len(uow.cleanup.list()) == 1
    assert service.cleanup_pending() == 1
    assert not service.storage.resolve("p", output_paths["source"]).exists()
    assert service.storage.resolve("p", output_paths["target"]).read_bytes() == b"target"
    record = service.archive.list()[0]
    assert service.archive.storage.verify(record.files[0])
    assert service.cleanup_pending() == 0


@pytest.mark.parametrize("snapshot", ["assets", "context", "execution", "prompt"])
def test_completed_history_keeps_old_input_until_last_consumer_is_deleted(
    deletion, output_paths, snapshot,
):
    service, lifecycle, factory = deletion
    media = {"projectRelativePath": output_paths["source"]}
    with factory() as uow:
        if snapshot == "prompt":
            uow.prompt_batches.add(PromptEnhancementBatch("batch", "p", "completed", 1))
            uow.prompt_jobs.add(PromptEnhancementJob(
                "history", "batch", "p", "target", JobStatus.COMPLETED,
                {"media": [media]}, {}, {}, "minimax-h3",
            ))
        else:
            uow.jobs.add(Job(
                "history", "p", "target", JobStatus.COMPLETED, "prompt", {},
                [media] if snapshot == "assets" else [], {}, {}, {},
                {"media": [media]} if snapshot == "context" else {},
                execution_context={"media": [media]} if snapshot == "execution" else None,
            ))
    lifecycle.transition_tasks("p", ["source"], "trash")
    service.purge_tasks("p", ["source"])
    service.cleanup_pending()
    original = service.storage.resolve("p", output_paths["source"])
    assert original.read_bytes() == b"source"
    lifecycle.transition_tasks("p", ["target"], "trash")
    service.purge_tasks("p", ["target"])
    service.cleanup_pending()
    assert not original.exists()


def test_project_purge_archives_every_version_and_cleans_owned_files(deletion, tmp_path):
    service, lifecycle, factory = deletion
    outside = tmp_path / "export.mp4"
    outside.write_bytes(b"keep exported file")
    lifecycle.transition_project("p", "trash")
    outcome = service.purge_project("p")
    assert outcome.archived_result_count == 2
    with factory() as uow:
        assert uow.projects.get("p") is None
        assert uow.contexts.list_by_target("target") == []
    assert service.cleanup_pending() == 1
    assert service.storage.files("p") == set()
    assert outside.read_bytes() == b"keep exported file"
    assert all(service.archive.storage.verify(r.files[0]) for r in service.archive.list())


def test_project_purge_preserves_unregistered_files_inside_project_directory(deletion):
    service, lifecycle, factory = deletion
    root = service.storage.resolve("p")
    asset = AssetService(factory, service.archive.media).import_bytes(
        "p", "imported.txt", b"managed copy"
    )
    thumbnail = root / "thumbnails" / "owned.png"
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.write_bytes(b"managed thumbnail")
    with factory() as uow:
        stored = uow.assets.get(asset.id)
        stored.thumbnail_path = "thumbnails/owned.png"
        uow.assets.update(stored)
    exports = [root / "my-export.mp4", root / "assets" / "unregistered-original.png"]
    for path in exports:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"user-owned")
    lifecycle.transition_project("p", "trash")
    service.purge_project("p", archive_results=False)
    assert service.cleanup_pending() == 1
    assert all(path.read_bytes() == b"user-owned" for path in exports)
    assert not service.storage.resolve("p", asset.project_relative_path).exists()
    assert not thumbnail.exists()
    assert service.storage.files("p") == {
        "my-export.mp4", "assets/unregistered-original.png",
    }


@pytest.mark.parametrize("resolved_context", [False, True])
def test_context_cache_is_kept_until_last_snapshot_owner_is_deleted(deletion, resolved_context):
    service, lifecycle, factory = deletion
    relative = "context/" + "a" * 64 + ".png"
    cache = service.storage.resolve("p", relative)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"shared context")
    with factory() as uow:
        for task in ("source", "target"):
            context = {"media": [{"projectRelativePath": relative}]}
            job = replace(
                uow.jobs.get(f"job-{task}"), id=f"cache-job-{task}",
                context_snapshot={} if resolved_context else context,
                execution_context=context if resolved_context else None,
            )
            uow.jobs.add(job)
    lifecycle.transition_tasks("p", ["source"], "trash")
    service.purge_tasks("p", ["source"], archive_results=False)
    assert service.cleanup_pending() == 1
    assert cache.read_bytes() == b"shared context"
    lifecycle.transition_tasks("p", ["target"], "trash")
    service.purge_tasks("p", ["target"], archive_results=False)
    assert service.cleanup_pending() == 1
    assert not cache.exists()


def test_project_purge_cleans_snapshot_cache_but_not_unowned_cache(deletion):
    service, lifecycle, factory = deletion
    relative = "context/" + "a" * 64 + ".mp4"
    owned = service.storage.resolve("p", relative)
    unknown = owned.with_name("b" * 64 + ".mp4")
    owned.parent.mkdir(parents=True, exist_ok=True)
    owned.write_bytes(b"owned")
    unknown.write_bytes(b"unknown")
    with factory() as uow:
        uow.jobs.add(replace(
            uow.jobs.get("job-source"), id="cache-owner",
            context_snapshot={"media": [{"projectRelativePath": relative}]},
        ))
    lifecycle.transition_project("p", "trash")
    service.purge_project("p", archive_results=False)
    assert service.cleanup_pending() == 1
    assert not owned.exists()
    assert unknown.read_bytes() == b"unknown"


def test_archive_failure_rolls_back_entire_deletion(deletion, monkeypatch, output_paths):
    service, lifecycle, factory = deletion
    lifecycle.transition_project("p", "trash")

    def fail_copy(source):
        raise OSError("disk full")

    monkeypatch.setattr(service.archive.storage, "copy", fail_copy)
    with pytest.raises(ShotMillError) as error:
        service.purge_project("p")
    assert error.value.code == "RESULT_ARCHIVE_FAILED"
    with factory() as uow:
        assert uow.projects.get("p").deleted_at is not None
        assert uow.tasks.get("source") is not None
        assert uow.results.get("result-source") is not None
        assert uow.cleanup.list() == []
        assert uow.archived_results.list() == []
    assert service.storage.resolve("p", output_paths["source"]).read_bytes() == b"source"


def test_cleanup_failure_is_durable_and_retryable(deletion, monkeypatch):
    service, lifecycle, factory = deletion
    lifecycle.transition_tasks("p", ["source"], "trash")
    service.purge_tasks("p", ["source"], archive_results=False)
    original_delete = service.storage.delete_file

    def fail_delete(*args):
        raise PermissionError("file locked")

    monkeypatch.setattr(service.storage, "delete_file", fail_delete)
    assert service.cleanup_pending() == 0
    with factory() as uow:
        assert uow.cleanup.list()[0].last_error == "file locked"
    monkeypatch.setattr(service.storage, "delete_file", original_delete)
    resumed = PermanentDeleteService(factory, service.archive, service.storage)
    assert resumed.cleanup_pending() == 1
    assert service.archive.list() == []


@pytest.mark.parametrize("kind", ["video", "prompt"])
@pytest.mark.parametrize("active", [JobStatus.QUEUED, JobStatus.RUNNING])
@pytest.mark.parametrize("terminal", [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED])
def test_active_downstream_job_retains_media_through_history_until_purge(
    deletion, output_paths, providers, kind, active, terminal,
):
    service, lifecycle, factory = deletion
    lifecycle.transition_tasks("p", ["source"], "trash")
    snapshot = {"media": [{
        "projectRelativePath": output_paths["source"],
        "sourceTaskId": "source", "sourceResultId": "result-source",
        "assetId": "frozen-context", "reference": "<Video 1>", "mediaType": "video",
        "originalFilename": "source.mp4", "sha256": sha256(b"source").hexdigest(),
    }]}
    with factory() as uow:
        if kind == "video":
            uow.jobs.add(replace(
                uow.jobs.get("job-target"), id="busy-input", status=active,
                context_snapshot=deepcopy(snapshot), assets_snapshot=[],
            ))
        else:
            uow.prompt_batches.add(PromptEnhancementBatch(
                id="input-batch", project_id="p", status="running", total_count=1,
            ))
            uow.prompt_jobs.add(PromptEnhancementJob(
                id="busy-input", batch_id="input-batch", project_id="p", task_id="target",
                status=active, source_snapshot={"userPrompt": "frozen"},
                context_snapshot=deepcopy(snapshot), provider_profile_snapshot={},
                target_skill="test",
            ))
    with factory() as uow:
        repository = uow.jobs if kind == "video" else uow.prompt_jobs
        frozen = deepcopy(repository.get("busy-input"))
    service.purge_tasks("p", ["source"])
    assert service.cleanup_pending() == 0
    assert service.storage.resolve("p", output_paths["source"]).read_bytes() == b"source"
    # A fresh cleanup service must honor the persisted job and cleanup manifest.
    restarted = PermanentDeleteService(factory, service.archive, service.storage)
    assert restarted.cleanup_pending() == 0
    with factory() as uow:
        repository = uow.jobs if kind == "video" else uow.prompt_jobs
        job = repository.get("busy-input")
        assert job == frozen
        if kind == "video":
            generation = GenerationService(
                factory, providers[1], service.archive.media, ProjectEventBus(),
            )
            request = generation._provider_request(job)
            assert request.assets[0].path.read_bytes() == b"source"
        assert uow.tasks.get("source") is None
        assert len(uow.cleanup.list()) == 1
        job.status = terminal
        if kind == "video":
            repository.update_runtime(job)
        else:
            repository.update(job)
    assert restarted.cleanup_pending() == 1
    assert service.storage.resolve("p", output_paths["source"]).read_bytes() == b"source"
    with factory() as uow:
        repository = uow.jobs if kind == "video" else uow.prompt_jobs
        assert repository.get("busy-input").context_snapshot == snapshot
        assert uow.cleanup.list() == []
    lifecycle.transition_tasks("p", ["target"], "trash")
    restarted.purge_tasks("p", ["target"])
    assert restarted.cleanup_pending() == 1
    assert not service.storage.resolve("p", output_paths["source"]).exists()
    with factory() as uow:
        repository = uow.jobs if kind == "video" else uow.prompt_jobs
        assert repository.get("busy-input") is None
        assert uow.cleanup.list() == []


def test_purge_requires_trash_and_idle_and_valid_selection(deletion):
    service, lifecycle, factory = deletion
    with pytest.raises(ConflictError, match="回收站"):
        service.purge_tasks("p", ["source"])
    with pytest.raises(ConflictError, match="回收站"):
        service.purge_project("p")
    lifecycle.transition_tasks("p", ["source"], "trash")
    with factory() as uow:
        job = uow.jobs.get("job-source")
        job.status = JobStatus.QUEUED
        uow.jobs.update_runtime(job)
    with pytest.raises(ConflictError) as error:
        service.purge_tasks("p", ["source"])
    assert error.value.code == "TASK_BUSY"
    with pytest.raises(ShotMillError):
        service.purge_tasks("p", [])
    with factory() as uow:
        assert uow.tasks.get("source") is not None
        assert uow.cleanup.list() == []


@pytest.mark.parametrize("kind", ["video", "prompt"])
@pytest.mark.parametrize("active", [JobStatus.QUEUED, JobStatus.RUNNING])
@pytest.mark.parametrize("terminal", [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED])
def test_unsaved_input_asset_cannot_be_deleted_while_job_needs_it(
    deletion, kind, active, terminal,
):
    service, _, factory = deletion
    assets = AssetService(factory, service.archive.media)
    asset = assets.import_bytes("p", "input.txt", b"frozen input")
    unused = assets.import_bytes("p", "unused.txt", b"unrelated")
    media = [{"assetId": asset.id, "reference": "<Picture 1>", "role": "reference"}]
    with factory() as uow:
        assert uow.assets.binding_count(asset.id) == 0
        if kind == "video":
            uow.jobs.add(replace(
                uow.jobs.get("job-target"), id="needs-input", status=active,
                assets_snapshot=deepcopy(media),
            ))
        else:
            uow.prompt_batches.add(PromptEnhancementBatch(
                id="input-batch", project_id="p", status="running", total_count=1,
            ))
            uow.prompt_jobs.add(PromptEnhancementJob(
                id="needs-input", batch_id="input-batch", project_id="p", task_id="target",
                status=active, source_snapshot={"media": media}, context_snapshot={},
                provider_profile_snapshot={}, target_skill="test",
            ))
    with pytest.raises(ConflictError) as error:
        assets.delete("p", asset.id)
    assert error.value.code == "ASSET_IN_ACTIVE_JOB"
    assets.delete("p", unused.id)
    with factory() as uow:
        assert uow.assets.get(asset.id) is not None
        repository = uow.jobs if kind == "video" else uow.prompt_jobs
        job = repository.get("needs-input")
        job.status = terminal
        if kind == "video":
            repository.update_runtime(job)
        else:
            repository.update(job)
    assets.delete("p", asset.id)
    assert service.archive.media.resolve("p", asset.project_relative_path).read_bytes() == (
        b"frozen input"
    )


def test_batch_internal_references_leave_no_missing_target(deletion):
    service, lifecycle, factory = deletion
    lifecycle.transition_tasks("p", ["source", "target"], "trash")
    outcome = service.purge_tasks("p", ["source", "target"])
    assert set(outcome.deleted_ids) == {"source", "target"}
    with factory() as uow:
        assert uow.contexts.list_by_target("target") == []
        assert uow.projects.get("p") is not None


def test_permanent_delete_api_requires_confirmation_and_defaults_to_archive(deletion, client):
    service, lifecycle, _ = deletion
    client.app.state.container.permanent_delete_service = service
    lifecycle.transition_tasks("p", ["source"], "trash")
    path = "/api/v1/projects/p/tasks/permanent-delete"
    assert client.post(path, json={"taskIds": ["source"]}).status_code == 422
    assert client.post(path, json={"taskIds": ["source"], "confirmed": False}).status_code == 422
    response = client.post(path, json={"taskIds": ["source"], "confirmed": True})
    assert response.status_code == 200
    assert response.json()["archivedResultCount"] == 1
    assert response.json()["deletedIds"] == ["source"]
    lifecycle.transition_project("p", "trash")
    response = client.post("/api/v1/projects/p/permanent-delete", json={
        "confirmed": True, "archiveResults": False,
    })
    assert response.status_code == 200
    assert response.json()["archivedResultCount"] == 0
    assert len(service.archive.list()) == 1


def test_shared_live_result_file_is_not_removed(deletion, output_paths):
    service, lifecycle, factory = deletion
    with factory() as uow:
        uow.results.add(Result(
            id="shared", project_id="p", task_id="target", job_id="job-target",
            video_url=MediaStorage.media_url("p", output_paths["source"]),
        ))
    lifecycle.transition_tasks("p", ["source"], "trash")
    service.purge_tasks("p", ["source"], archive_results=False)
    assert service.cleanup_pending() == 1
    assert service.storage.resolve("p", output_paths["source"]).exists()


def test_delete_database_failure_keeps_source_and_rolls_back_archive(
    deletion, monkeypatch, output_paths
):
    from shotmill.persistence.repositories.project_asset import SqlAlchemyProjectRepository

    service, lifecycle, factory = deletion
    lifecycle.transition_project("p", "trash")

    def fail_delete(*args):
        raise RuntimeError("injected database failure")

    monkeypatch.setattr(SqlAlchemyProjectRepository, "delete", fail_delete)
    with pytest.raises(RuntimeError, match="database failure"):
        service.purge_project("p")
    with factory() as uow:
        assert uow.projects.get("p") is not None
        assert uow.results.get("result-source") is not None
        assert uow.archived_results.list() == []
        assert uow.cleanup.list() == []
    assert service.storage.resolve("p", output_paths["source"]).read_bytes() == b"source"
