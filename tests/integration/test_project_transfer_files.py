from io import BytesIO

import pytest
from shotmill.application.project_transfer_files import collect_project_transfer_files
from shotmill.application.project_transfer_source import read_project_transfer_source
from shotmill.domain.entities import AiPromptRevision, Job, PromptEnhancementJob, Result
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError
from shotmill.media.cleanup_storage import CleanupStorage
from shotmill.media.project_package import open_project_package, write_project_package
from test_batch_review_api import _project


def test_transfer_collects_shared_aliases_legacy_and_history_into_deduplicated_zip(client):
    container = client.app.state.container
    project = _project(client)["id"]
    first = container.asset_service.import_bytes(project, "first.png", b"same")
    second = container.asset_service.import_bytes(project, "second.png", b"same")
    legacy_path = container.storage.write_output(project, "old", "clip.mp4", b"legacy")
    context_path = container.storage.write_output(project, "context", "frame.png", b"frame")
    with container.generation_service.uow_factory() as uow:
        source = read_project_transfer_source(uow, project)
        source.results = [Result("r", project, "t", "j", f"/media/{project}/{legacy_path}")]
        source.jobs = [Job(
            "j", project, "t", JobStatus.COMPLETED, "", {}, [], {}, {}, {},
            {"media": [{"projectRelativePath": context_path}]},
        )]
        files = collect_project_transfer_files(
            uow, source, container.file_library, CleanupStorage(container.storage.projects_root),
        )
        assert set(files) == {
            first.project_relative_path, second.project_relative_path, legacy_path, context_path,
        }
        assert files[first.project_relative_path] == files[second.project_relative_path]
        package = BytesIO()
        write_project_package(package, {}, files)
    package.seek(0)
    with open_project_package(package) as staged:
        assert staged.files[first.project_relative_path].read_bytes() == b"same"
        assert staged.files[legacy_path].read_bytes() == b"legacy"
        assert staged.files[context_path].read_bytes() == b"frame"


@pytest.mark.parametrize("url", [
    "/media/foreign/output.mp4", "https://example.com/output.mp4",
    "/media/{project}/../outside.mp4", "/media/{project}/C:/private.mp4",
])
def test_transfer_rejects_foreign_or_escaping_result_paths(client, url):
    container = client.app.state.container
    project = _project(client)["id"]
    with container.generation_service.uow_factory() as uow:
        source = read_project_transfer_source(uow, project)
        source.results = [Result("r", project, "t", "j", url.format(project=project))]
        with pytest.raises((ConflictError, ValueError)):
            collect_project_transfer_files(
                uow, source, container.file_library,
                CleanupStorage(container.storage.projects_root),
            )


def test_transfer_rejects_foreign_shared_owner_even_when_bytes_exist(client):
    container = client.app.state.container
    project, other = _project(client)["id"], _project(client)["id"]
    asset = container.asset_service.import_bytes(other, "foreign.png", b"foreign")
    with container.generation_service.uow_factory() as uow:
        source = read_project_transfer_source(uow, project)
        source.results = [Result(
            "r", project, "t", "j", f"/media/{project}/{asset.project_relative_path}",
        )]
        with pytest.raises(ConflictError):
            collect_project_transfer_files(
                uow, source, container.file_library,
                CleanupStorage(container.storage.projects_root),
            )


def test_transfer_rejects_damaged_shared_content(client, monkeypatch):
    container = client.app.state.container
    project = _project(client)["id"]
    container.asset_service.import_bytes(project, "image.png", b"image")

    def damaged(file):
        raise OSError("Injected hash mismatch")

    monkeypatch.setattr(container.file_library.storage, "verify", damaged)
    with container.generation_service.uow_factory() as uow:
        source = read_project_transfer_source(uow, project)
        with pytest.raises(ConflictError) as error:
            collect_project_transfer_files(
                uow, source, container.file_library,
                CleanupStorage(container.storage.projects_root),
            )
        assert error.value.code == "PROJECT_TRANSFER_MEDIA_MISSING"


@pytest.mark.parametrize("has_snapshot", [False, True])
def test_revision_media_without_live_asset_requires_historical_file(client, has_snapshot):
    container = client.app.state.container
    project = _project(client)["id"]
    relative = container.storage.write_output(project, "history", "input.png", b"historical")
    with container.generation_service.uow_factory() as uow:
        source = read_project_transfer_source(uow, project)
        source.prompt_revisions = [AiPromptRevision(
            "revision", project, "task", "Original", "Enhanced", ["deleted-asset"],
            False, False, "minimax-h3", "1",
        )]
        if has_snapshot:
            source.prompt_jobs = [PromptEnhancementJob(
                "history", "batch", project, "task", JobStatus.COMPLETED,
                {"media": [{"assetId": "deleted-asset", "projectRelativePath": relative}]},
                {}, {}, "minimax-h3", revision_id="revision",
            )]
            files = collect_project_transfer_files(
                uow, source, container.file_library,
                CleanupStorage(container.storage.projects_root),
            )
            assert files[relative].read_bytes() == b"historical"
        else:
            with pytest.raises(ConflictError) as error:
                collect_project_transfer_files(
                    uow, source, container.file_library,
                    CleanupStorage(container.storage.projects_root),
                )
            assert error.value.code == "PROJECT_TRANSFER_HISTORY_MEDIA_MISSING"
