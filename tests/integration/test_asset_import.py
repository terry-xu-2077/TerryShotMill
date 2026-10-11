import pytest
from shotmill.application.asset_import_service import ImportSelection
from shotmill.domain.entities import Job, Project, Result, Task
from shotmill.domain.enums import JobStatus
from shotmill.errors import ShotMillError


@pytest.fixture
def imports(client):
    container = client.app.state.container

    def factory():
        return container.generation_service.uow_factory()

    for name in ("source", "target"):
        container.project_documents.register_new(
            name, container.settings.data_root / f"{name}.shotmill",
        )
    with factory() as uow:
        for name in ("source", "target"):
            uow.projects.add(Project(id=name, title=name))
        uow.tasks.add(Task(id="task", project_id="source", title="Video task", display_order=1))
        uow.jobs.add(
            Job(
                id="job",
                project_id="source",
                task_id="task",
                status=JobStatus.COMPLETED,
                final_prompt_snapshot="submitted prompt",
                task_content_snapshot={},
                assets_snapshot=[],
                generation_profile_snapshot={},
                provider_profile_snapshot={"api_key": "secret"},
                params_snapshot={"seed": 42},
                context_snapshot={},
            )
        )
        path = container.storage.write_output("source", "job", "video.mp4", b"video bytes")
        preview = container.storage.write_output("source", "job", "preview.png", b"preview bytes")
        uow.results.add(
            Result(
                id="result",
                project_id="source",
                task_id="task",
                job_id="job",
                video_url=container.storage.media_url("source", path),
                preview_url=container.storage.media_url("source", preview),
                metadata={"contentType": "video/mp4", "durationSeconds": 4, "width": 1280},
            )
        )
    asset = container.asset_service.import_bytes(
        "source", "sound.wav", b"sound bytes", name="Sound"
    )
    return container, factory, asset, client


def test_import_asset_and_result_survive_source_project_purge(imports):
    container, factory, source_asset, _ = imports
    imported = container.asset_import_service.import_sources(
        "target",
        [
            ImportSelection("asset", source_asset.id),
            ImportSelection("result", "result"),
        ],
    )
    assert len(imported) == 2
    audio, video = imported
    assert audio.id != source_asset.id
    assert audio.project_relative_path != source_asset.project_relative_path
    assert audio.original_filename == "sound.wav"
    assert audio.hash == source_asset.hash
    assert container.storage.resolve("target", audio.project_relative_path) == (
        container.storage.resolve("source", source_asset.project_relative_path)
    )
    assert video.provenance["prompt"] == "submitted prompt"
    assert video.provenance["params"] == {"seed": 42}
    assert "secret" not in repr(video.provenance)
    assert video.duration == 4
    container.removal_service.remove_project("source")
    with factory() as uow:
        assert uow.projects.get("source") is None
        reloaded = uow.assets.get(video.id)
        assert reloaded.provenance["projectTitle"] == "source"
        assert reloaded.thumbnail_path is not None
    assert (
        container.storage.resolve("target", audio.project_relative_path).read_bytes()
        == b"sound bytes"
    )
    assert (
        container.storage.resolve("target", video.project_relative_path).read_bytes()
        == b"video bytes"
    )
    assert (
        container.storage.resolve("target", video.thumbnail_path).read_bytes() == b"preview bytes"
    )


def test_import_existing_shared_asset_reuses_bytes_without_rewriting(imports, monkeypatch):
    container, factory, source_asset, _ = imports

    def unexpected_write(*args, **kwargs):
        pytest.fail("an already-managed object must be verified and referenced, not copied")

    monkeypatch.setattr(container.file_library.storage, "put", unexpected_write)
    imported = container.asset_import_service.import_sources(
        "target", [ImportSelection("asset", source_asset.id)],
    )[0]
    assert imported.id != source_asset.id
    with factory() as uow:
        refs = uow.files.references(source_asset.hash)
        assert {ref.scope_id for ref in refs} == {"source", "target"}


def test_reimport_preserves_preview_name_and_mime_without_physical_extension(imports):
    container, factory, _, client = imports
    first = container.asset_import_service.import_sources(
        "target", [ImportSelection("result", "result")],
    )[0]
    with factory() as uow:
        container.project_documents.register_new(
            "third", container.settings.data_root / "third.shotmill",
        )
        uow.projects.add(Project(id="third", title="Third"))
    second = container.asset_import_service.import_sources(
        "third", [ImportSelection("asset", first.id)],
    )[0]
    preview = container.project_file_reader.read("third", second.thumbnail_path)
    assert preview.filename == "preview.png"
    assert preview.mime_type == "image/png"
    assert preview.path == container.storage.resolve("target", first.thumbnail_path)
    url = container.storage.media_url("third", second.thumbnail_path)
    assert client.get(url).headers["content-type"] == "image/png"
    container.removal_service.remove_project("target")
    assert client.get(url).content == b"preview bytes"


def test_batch_copy_failure_rolls_back_records(imports, monkeypatch):
    container, factory, source_asset, _ = imports
    service = container.asset_import_service
    original = service.file_library.import_path
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.file_library, "import_path", fail_second)
    with pytest.raises(ShotMillError) as error:
        service.import_sources(
            "target",
            [
                ImportSelection("asset", source_asset.id),
                ImportSelection("result", "result"),
            ],
        )
    assert error.value.code == "ASSET_IMPORT_FAILED"
    with factory() as uow:
        assert uow.assets.list_by_project("target") == []
        assert uow.results.get("result") is not None
        assert all(ref.scope_id != "target" for ref in uow.files.references(source_asset.hash))
    assert (
        container.storage.resolve("source", source_asset.project_relative_path).read_bytes()
        == b"sound bytes"
    )


def test_import_checksum_mismatch_is_rejected(imports):
    container, factory, source_asset, _ = imports
    container.storage.resolve("source", source_asset.project_relative_path).write_bytes(b"changed")
    with pytest.raises(ShotMillError) as error:
        container.asset_import_service.import_sources(
            "target", [ImportSelection("asset", source_asset.id)]
        )
    assert error.value.code == "ASSET_IMPORT_FAILED"
    with factory() as uow:
        assert uow.assets.list_by_project("target") == []


def test_empty_preview_rolls_back_shared_import_without_touching_source_result(imports):
    container, factory, _, _ = imports
    with factory() as uow:
        result = uow.results.get("result")
    container.asset_import_service._result_path("source", result.preview_url).write_bytes(b"")
    with pytest.raises(ShotMillError) as error:
        container.asset_import_service.import_sources(
            "target", [ImportSelection("result", "result")],
        )
    assert error.value.code == "ASSET_IMPORT_FAILED"
    with factory() as uow:
        assert uow.assets.list_by_project("target") == []
        assert uow.results.get("result") is not None


def test_import_api_exposes_read_only_provenance_and_checks_selection(imports):
    container, factory, source_asset, client = imports
    path = "/api/v1/projects/target/assets/import"
    payload = {"sources": [{"kind": "asset", "id": source_asset.id}]}
    response = client.post(path, json=payload)
    assert response.status_code == 201
    asset = response.json()[0]
    assert asset["provenance"]["sourceId"] == source_asset.id
    assert asset["originalFileName"] == "sound.wav"
    assert client.post(path, json={"sources": []}).status_code == 422
    assert client.post(path, json={"sources": payload["sources"] * 2}).status_code == 422
    assert client.post(path, json={"sources": [{"kind": "archive", "id": "old"}]}).status_code == 422
    assert (
        client.post(path, json={"sources": [{"kind": "result", "id": "missing"}]}).status_code
        == 404
    )
    assert (
        client.post(
            path, json={"sources": [{"kind": "url", "id": "https://example.com"}]}
        ).status_code
        == 422
    )
    container.asset_service.update("target", asset["id"], name="New name")
    with factory() as uow:
        assert uow.assets.get(asset["id"]).provenance["sourceId"] == source_asset.id


def test_import_candidates_only_include_open_projects(imports):
    container, _, source_asset, client = imports
    path = "/api/v1/projects/target/assets/import-sources"
    response = client.get(path)
    assert response.status_code == 200
    assert {(item["kind"], item["id"]) for item in response.json()} == {
        ("asset", source_asset.id),
        ("result", "result"),
    }
    assert client.get(path + "?sourceProjectId=missing").json() == []
    container.removal_service.remove_project("source")
    assert client.get(path).json() == []
