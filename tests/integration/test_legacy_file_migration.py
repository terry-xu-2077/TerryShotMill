import pytest
from shotmill.application.asset_import_service import ImportSelection
from shotmill.application.asset_service import AssetService
from shotmill.application.legacy_file_migration import LegacyFileMigration
from shotmill.application.snapshot_files import freeze_media_references
from shotmill.domain.entities import Job, PromptEnhancementBatch, PromptEnhancementJob, Result
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.legacy_paths import legacy_owner_id
from shotmill.media.project_package import open_project_package
from test_batch_review_api import _project, _task


def setup_migration(client):
    container = client.app.state.container
    factory = container.generation_service.uow_factory
    return container, AssetService(factory, container.storage), LegacyFileMigration(
        factory, container.file_library, CleanupStorage(container.settings.projects_root),
    )


def test_legacy_mapping_deduplicates_across_projects_without_changing_sources(client):
    container, assets, migration = setup_migration(client)
    for title in ("Left", "Right"):
        project = _project(client)["id"]
        asset = assets.import_bytes(project, f"{title}.png", b"same-content")
        original = container.storage.resolve(project, asset.project_relative_path)
        assert migration.migrate_project(project) == 1
        assert migration.migrate_project(project) == 1
        with migration.factory() as uow:
            assert uow.assets.get(asset.id).project_relative_path == asset.project_relative_path
            reference = uow.files.get_reference(
                "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
                "content",
            )
            assert container.file_library.resolve(uow, reference).read_bytes() == b"same-content"
        assert original.read_bytes() == b"same-content"
    assert len(list(container.settings.files_root.glob("objects/*/*"))) == 1


def test_missing_legacy_file_rolls_back_all_mappings_and_retry_succeeds(client):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    items = [
        assets.import_bytes(project, f"{index}.png", str(index).encode()) for index in range(2)
    ]
    last = max(items, key=lambda asset: asset.project_relative_path)
    missing = container.storage.resolve(project, last.project_relative_path)
    payload = missing.read_bytes()
    missing.unlink()
    with pytest.raises(FileNotFoundError):
        migration.migrate_project(project)
    with migration.factory() as uow:
        for asset in items:
            assert uow.files.get_reference(
                "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
                "content",
            ) is None
    missing.write_bytes(payload)
    assert migration.migrate_project(project) == 2
    missing.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="checksum"):
        migration.migrate_project(project)


def test_old_address_reads_migrated_content_after_source_removed(client):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    other = _project(client)["id"]
    asset = assets.import_bytes(project, "sample.png", b"0123456789")
    relative = asset.project_relative_path
    url = container.storage.media_url(project, relative)
    assert client.get(url).content == b"0123456789"
    migration.migrate_project(project)
    container.storage.resolve(project, relative).unlink()
    assert container.storage.resolve_read(project, relative).read_bytes() == b"0123456789"
    response = client.get(url, headers={"Range": "bytes=2-5"})
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-type"] == "image/png"
    assert client.head(url).headers["content-length"] == "10"
    assert client.get(container.storage.media_url(other, relative)).status_code == 404
    assert migration.migrate_project(project) == 1
    with container.project_export_service.prepare(project) as package_path:
        with package_path.open("rb") as stream, open_project_package(stream) as package:
            assert package.files[relative].read_bytes() == b"0123456789"


def test_mapped_file_is_authoritative_and_missing_blob_does_not_fall_back(client):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    asset = assets.import_bytes(project, "sample.png", b"original")
    relative = asset.project_relative_path
    migration.migrate_project(project)
    container.storage.resolve(project, relative).write_bytes(b"changed legacy copy")
    url = container.storage.media_url(project, relative)
    assert client.get(url).content == b"original"
    container.storage.resolve_read(project, relative).unlink()
    assert client.get(url).status_code == 404


def test_migrated_legacy_media_can_be_imported_and_archived_without_old_copies(client):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    target = _project(client)["id"]
    task = _task(client, project, "Legacy", "Prompt")["id"]
    asset = assets.import_bytes(project, "source.png", b"image")
    relative = container.storage.write_output(project, "legacy-job", "clip.mp4", b"video")
    with migration.factory() as uow:
        uow.jobs.add(Job(
            id="legacy-job", project_id=project, task_id=task, status=JobStatus.COMPLETED,
            final_prompt_snapshot="Prompt", task_content_snapshot={}, assets_snapshot=[],
            generation_profile_snapshot={}, provider_profile_snapshot={}, params_snapshot={},
            context_snapshot={},
        ))
        uow.results.add(Result(
            id="legacy-result", project_id=project, task_id=task, job_id="legacy-job",
            video_url=container.storage.media_url(project, relative),
            metadata={"contentType": "video/mp4"},
        ))
    assert migration.migrate_project(project) == 2
    for path in (relative, asset.project_relative_path):
        container.storage.resolve(project, path).unlink()
    imported = container.asset_import_service.import_sources(target, [
        ImportSelection("asset", asset.id), ImportSelection("result", "legacy-result"),
    ])
    assert [container.storage.resolve_read(target, item.project_relative_path).read_bytes()
            for item in imported] == [b"image", b"video"]
    assert [item.original_filename for item in imported] == ["source.png", "clip.mp4"]
    record = container.result_archive_service.archive_tasks(project, [task])[0]
    assert container.result_archive_service.file(record.id, 0)[0].read_bytes() == b"video"
    assert record.files[0]["filename"] == "clip.mp4"
    assert len(list(container.settings.files_root.glob("objects/*/*"))) == 2
    container.lifecycle_service.transition_project(project, "trash")
    container.permanent_delete_service.purge_project(project)
    container.permanent_delete_service.cleanup_pending()
    with migration.factory() as uow:
        assert uow.projects.get(project) is None
        for item in imported:
            assert not any(ref.scope_kind == "project" and ref.scope_id == project
                           for ref in uow.files.references(item.hash))
    assert container.result_archive_service.file(record.id, 0)[0].read_bytes() == b"video"
    assert [container.storage.resolve_read(target, item.project_relative_path).read_bytes()
            for item in imported] == [b"image", b"video"]


def test_new_snapshot_owns_migrated_input_independently_of_legacy_alias(client):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    asset = assets.import_bytes(project, "source.png", b"image")
    migration.migrate_project(project)
    media = [{"assetId": asset.id, "projectRelativePath": asset.project_relative_path}]
    with migration.factory() as uow:
        frozen = freeze_media_references(uow, project, "job", "new-job", media)
        assert frozen[0]["projectRelativePath"] == "shared/job/new-job/input-0"
        assert media[0]["projectRelativePath"] == asset.project_relative_path
        uow.files.release_owner(
            "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
        )
    container.storage.resolve(project, asset.project_relative_path).unlink()
    resolved = container.storage.resolve_read(project, frozen[0]["projectRelativePath"])
    assert resolved.read_bytes() == b"image"


@pytest.mark.parametrize("kind", ["video", "prompt"])
@pytest.mark.parametrize("state", [JobStatus.QUEUED, JobStatus.RUNNING])
def test_migration_rejects_active_work_before_copying_any_file(client, monkeypatch, kind, state):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    task = _task(client, project, "Active", "Prompt")["id"]
    asset = assets.import_bytes(project, "source.png", b"image")
    with migration.factory() as uow:
        if kind == "video":
            uow.jobs.add(Job("busy-job", project, task, state, "Prompt", {}, [], {}, {}, {}, {}))
        else:
            uow.prompt_batches.add(PromptEnhancementBatch("busy-batch", project, "queued", 1))
            uow.prompt_jobs.add(PromptEnhancementJob(
                "busy-job", "busy-batch", project, task, state, {}, {}, {}, "minimax-h3",
            ))

    def forbid_copy(*args, **kwargs):
        pytest.fail("Migration copied a file before rejecting active work")

    monkeypatch.setattr(container.file_library, "import_path", forbid_copy)
    with pytest.raises(ConflictError) as error:
        migration.migrate_project(project)
    assert error.value.code == "PROJECT_TRANSFER_BUSY"
    assert container.storage.resolve(project, asset.project_relative_path).read_bytes() == b"image"
    assert not list(container.settings.files_root.glob("objects/*/*"))


@pytest.mark.parametrize("historical", [False, True])
def test_deleting_migrated_asset_releases_only_unused_legacy_mapping(client, historical):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    asset = assets.import_bytes(project, "source.png", b"image")
    if historical:
        task = _task(client, project, "History", "Prompt")["id"]
        other = _task(client, project, "Other history", "Prompt")["id"]
        with migration.factory() as uow:
            uow.jobs.add(Job(
                "history", project, task, JobStatus.COMPLETED, "Prompt", {},
                [{"assetId": asset.id, "projectRelativePath": asset.project_relative_path}],
                {}, {}, {}, {},
            ))
            uow.jobs.add(Job(
                "other-history", project, other, JobStatus.COMPLETED, "Prompt", {},
                [{"assetId": asset.id, "projectRelativePath": asset.project_relative_path}],
                {}, {}, {}, {},
            ))
    migration.migrate_project(project)
    shared = container.storage.resolve_read(project, asset.project_relative_path)
    container.asset_service.delete(project, asset.id)
    with migration.factory() as uow:
        mapping = uow.files.get_reference(
            "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
            "content",
        )
        assert (mapping is not None) == historical
    assert shared.read_bytes() == b"image"
    if historical:
        container.lifecycle_service.transition_tasks(project, [task], "trash")
        container.permanent_delete_service.purge_tasks(project, [task])
        with migration.factory() as uow:
            assert uow.files.get_reference(
                "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
                "content",
            ) is not None
        assert container.storage.resolve_read(project, asset.project_relative_path) == shared
        container.lifecycle_service.transition_tasks(project, [other], "trash")
        container.permanent_delete_service.purge_tasks(project, [other])
        with migration.factory() as uow:
            assert uow.files.get_reference(
                "project", project, "legacy_path", legacy_owner_id(asset.project_relative_path),
                "content",
            ) is None
        assert shared.read_bytes() == b"image"


@pytest.mark.parametrize("unsupported_field", [False, True])
def test_old_prompt_context_media_survives_migration_export_and_import(client, unsupported_field):
    container, assets, migration = setup_migration(client)
    project = _project(client)["id"]
    task = _task(client, project, "Prompt history", "Prompt")["id"]
    asset = assets.import_bytes(project, "old.png", b"context bytes")
    with migration.factory() as uow:
        uow.prompt_batches.add(PromptEnhancementBatch("batch", project, "completed", 1))
        uow.prompt_jobs.add(PromptEnhancementJob(
            "history", "batch", project, task, JobStatus.COMPLETED, {"userPrompt": "Prompt"},
            {"media": [{"assetId": asset.id, "sourceTaskId": task,
                        "projectRelativePath": asset.project_relative_path,
                        "originalFilename": "old.png", "mediaType": "image",
                        **({"apiKey": "must-not-export"} if unsupported_field else {})}]},
            {}, "minimax-h3",
        ))
    container.asset_service.delete(project, asset.id)
    assert migration.migrate_project(project) == 1
    container.storage.resolve(project, asset.project_relative_path).unlink()
    exported = client.get(f"/api/v1/projects/{project}/export")
    if unsupported_field:
        assert exported.status_code == 409
        assert "PROJECT_TRANSFER_SCHEMA_UNSUPPORTED" in exported.text
        assert "must-not-export" not in exported.text
        return
    assert exported.status_code == 200, exported.text
    imported = client.post("/api/v1/projects/import", files={
        "file": ("history.zip", exported.content, "application/zip"),
    })
    assert imported.status_code == 201, imported.text
    destination = imported.json()["projectId"]
    with migration.factory() as uow:
        imported_task = uow.tasks.list_by_project(destination)[0]
        job = uow.prompt_jobs.list_by_task(imported_task.id)[0]
        media = job.context_snapshot["media"][0]
        assert media["sourceTaskId"] == imported_task.id
        assert media["assetId"] != asset.id
        assert "apiKey" not in media
        assert media["projectRelativePath"].startswith("shared/prompt_job/")
    resolved = container.storage.resolve_read(destination, media["projectRelativePath"])
    assert resolved.read_bytes() == b"context bytes"
