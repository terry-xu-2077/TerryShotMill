from dataclasses import replace

import pytest
from shotmill.application.asset_import_service import ImportSelection
from shotmill.domain.files import FileReference
from shotmill.errors import ConflictError, NotFoundError
from shotmill.persistence.repositories.archive import SqlAlchemyArchivedResultRepository
from shotmill.persistence.repositories.task import SqlAlchemyTaskRepository
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def generated(client):
    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    project = _project(client)["id"]
    task = _task(client, project, "Archive", "Generate")["id"]
    response = client.post(f"/api/v1/projects/{project}/tasks/{task}/generation", json={})
    assert response.status_code == 202
    client.portal.call(service.execute, response.json()["id"])
    with service.uow_factory() as uow:
        result = uow.results.list_by_task(task)[0]
    return container, project, task, result


def test_archive_delete_releases_only_its_references_and_preserves_import(client):
    container, project, task, result = generated(client)
    service = container.result_archive_service
    archive = service.archive_tasks(project, [task])[0]
    path, _ = service.file(archive.id, 0)
    target = _project(client)["id"]
    imported = container.asset_import_service.import_sources(
        target, [ImportSelection("archive", archive.id)],
    )[0]
    response = client.delete(f"/api/v1/result-archive/{archive.id}")
    assert response.status_code == 204, response.text
    assert response.content == b""
    assert client.get(f"/api/v1/result-archive/{archive.id}/files/0").status_code == 404
    assert all(item["id"] != archive.id
               for item in client.get("/api/v1/result-archive").json())
    with service.uow_factory() as uow:
        assert uow.archived_results.get(archive.id) is None
        references = uow.files.references(archive.files[0]["sha256"])
        assert not any(ref.scope_kind == "archive" and ref.scope_id == archive.id
                       for ref in references)
        assert any(ref.owner_id == result.id for ref in references)
        assert any(ref.owner_id == imported.id for ref in references)
    assert path.read_bytes() == b"fake-video-bytes"
    assert client.get(result.video_url).content == b"fake-video-bytes"
    assert client.get(f"/media/{target}/{imported.project_relative_path}").content == (
        b"fake-video-bytes"
    )
    with pytest.raises(NotFoundError):
        service.file(archive.id, 0)
    with pytest.raises(NotFoundError):
        service.delete(archive.id)
    assert client.delete(f"/api/v1/result-archive/{archive.id}").status_code == 404


def test_archive_delete_failure_rolls_back_released_references(client, monkeypatch):
    container, project, task, _ = generated(client)
    service = container.result_archive_service
    archive = service.archive_tasks(project, [task])[0]
    with service.uow_factory() as uow:
        before = uow.files.references(archive.files[0]["sha256"])

    def fail(self, archive_id):
        from shotmill.persistence.repositories.files import SqlAlchemyFileRepository
        refs = SqlAlchemyFileRepository(self.session).references(archive.files[0]["sha256"])
        assert not any(ref.scope_kind == "archive" and ref.scope_id == archive_id for ref in refs)
        raise RuntimeError("injected archive deletion failure")

    monkeypatch.setattr(SqlAlchemyArchivedResultRepository, "delete", fail)
    with pytest.raises(RuntimeError, match="injected"):
        service.delete(archive.id)
    with service.uow_factory() as uow:
        assert uow.archived_results.get(archive.id) is not None
        assert uow.files.references(archive.files[0]["sha256"]) == before
    assert service.file(archive.id, 0)[0].read_bytes() == b"fake-video-bytes"


@pytest.mark.parametrize("missing", [False, True])
def test_last_archive_can_be_deleted_after_source_purge_even_when_media_is_missing(client, missing):
    container, project, task, _ = generated(client)
    service = container.result_archive_service
    archive = service.archive_tasks(project, [task])[0]
    path, _ = service.file(archive.id, 0)
    digest = archive.files[0]["sha256"]
    container.lifecycle_service.transition_tasks(project, [task], "trash")
    container.permanent_delete_service.purge_tasks(project, [task], archive_results=False)
    with service.uow_factory() as uow:
        assert all(ref.scope_kind == "archive" and ref.scope_id == archive.id
                   for ref in uow.files.references(digest))
    if missing:
        # This path belongs to the fixture's isolated temporary data directory.
        path.unlink()
        assert client.get(f"/api/v1/result-archive/{archive.id}/files/0").status_code == 409
    assert client.delete(f"/api/v1/result-archive/{archive.id}").status_code == 204
    with service.uow_factory() as uow:
        assert uow.files.references(digest) == []
        assert uow.archived_results.get(archive.id) is None
        assert uow.files.get(digest) is not None
    assert path.exists() == (not missing)


def test_deleting_one_archive_preserves_another_archive_of_identical_content(client):
    container, project, task, _ = generated(client)
    service = container.result_archive_service
    first = service.archive_tasks(project, [task])[0]
    _, other_project, other_task, _ = generated(client)
    second = service.archive_tasks(other_project, [other_task])[0]
    assert first.files[0]["sha256"] == second.files[0]["sha256"]
    service.delete(first.id)
    assert service.file(second.id, 0)[0].read_bytes() == b"fake-video-bytes"
    with service.uow_factory() as uow:
        refs = uow.files.references(second.files[0]["sha256"])
        assert any(ref.scope_kind == "archive" and ref.scope_id == second.id for ref in refs)
        assert not any(ref.scope_kind == "archive" and ref.scope_id == first.id for ref in refs)


def test_archive_reuses_global_bytes_and_survives_source_reference_release(client, monkeypatch):
    container, project, task, result = generated(client)
    library = container.file_library

    def no_rewrite(*args, **kwargs):
        pytest.fail("managed result/archive content must be reused, not rewritten")

    monkeypatch.setattr(library.storage, "put", no_rewrite)
    archive = container.result_archive_service.archive_tasks(project, [task])[0]
    assert archive.files[0]["storage"] == "shared"
    with container.generation_service.uow_factory() as uow:
        uow.files.release_owner("project", project, "result", result.id)
        uow.projects.delete(project)
    path, filename = container.result_archive_service.file(archive.id, 0)
    assert filename == "result.mp4"
    assert path.read_bytes() == b"fake-video-bytes"
    target = _project(client)["id"]
    imported = container.asset_import_service.import_sources(
        target, [ImportSelection("archive", archive.id)],
    )[0]
    assert container.storage.resolve(target, imported.project_relative_path) == path
    assert len(list(container.settings.files_root.glob("objects/*/*"))) == 1
    assert not [p for p in container.settings.results_archive_root.rglob("*") if p.is_file()]


def test_archive_without_its_own_reference_cannot_borrow_another_owners_file(client):
    container, project, task, result = generated(client)
    archive = container.result_archive_service.archive_tasks(project, [task])[0]
    with container.generation_service.uow_factory() as uow:
        uow.files.release_owner("archive", archive.id, "result", result.id)
        assert uow.files.references(archive.files[0]["sha256"])
    with pytest.raises(ConflictError) as error:
        container.result_archive_service.file(archive.id, 0)
    assert error.value.code == "ARCHIVE_DAMAGED"
    with pytest.raises(ConflictError):
        container.result_archive_service.archive_tasks(project, [task])


def test_task_purge_releases_only_deleted_owners_and_preserves_shared_archive(client):
    container, project, task, result = generated(client)
    archive = container.result_archive_service.archive_tasks(project, [task])[0]
    target = _project(client)["id"]
    imported = container.asset_import_service.import_sources(
        target, [ImportSelection("archive", archive.id)],
    )[0]
    digest = archive.files[0]["sha256"]
    with container.generation_service.uow_factory() as uow:
        job = uow.jobs.list_by_task(task)[0]
        uow.files.bind(FileReference("project", project, "job", job.id, "input-0", digest))
    container.lifecycle_service.transition_tasks(project, [task], "trash")
    container.permanent_delete_service.purge_tasks(project, [task])
    with container.generation_service.uow_factory() as uow:
        references = uow.files.references(digest)
        assert not any(ref.scope_kind == "project" and ref.scope_id == project
                       and ref.owner_kind in {"result", "job"} for ref in references)
        assert any(ref.scope_kind == "archive" and ref.scope_id == archive.id
                   for ref in references)
        assert any(ref.scope_kind == "project" and ref.scope_id == target
                   and ref.owner_id == imported.id for ref in references)
    archived_path, _ = container.result_archive_service.file(archive.id, 0)
    assert archived_path.read_bytes() == b"fake-video-bytes"
    media = client.get(f"/media/{target}/{imported.project_relative_path}")
    assert media.content == b"fake-video-bytes"


def test_failed_task_purge_restores_references_and_does_not_publish_archive(client, monkeypatch):
    container, project, task, result = generated(client)
    factory = container.generation_service.uow_factory
    container.lifecycle_service.transition_tasks(project, [task], "trash")
    with factory() as uow:
        reference = uow.files.get_reference("project", project, "result", result.id, "output")
        before = uow.files.references(reference.sha256)

    def fail_delete(self, task_id):
        # Verify failure is injected after release, not before the new branch.
        from shotmill.persistence.repositories.files import SqlAlchemyFileRepository
        assert SqlAlchemyFileRepository(self.session).get_reference(
            "project", project, "result", result.id, "output",
        ) is None
        raise RuntimeError("injected task deletion failure")

    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyTaskRepository, "delete", fail_delete)
        with pytest.raises(RuntimeError, match="injected"):
            container.permanent_delete_service.purge_tasks(project, [task])
    with factory() as uow:
        assert uow.tasks.get(task) is not None
        assert uow.results.get(result.id) is not None
        assert uow.files.references(reference.sha256) == before
        assert uow.cleanup.list() == []
    assert container.result_archive_service.list() == []
    assert client.get(result.video_url).content == b"fake-video-bytes"
    assert container.permanent_delete_service.purge_tasks(project, [task]).deleted_ids == [task]


def test_task_purge_preserves_result_alias_used_by_another_historical_job(client):
    container, project, task, result = generated(client)
    consumer = _task(client, project, "Historical consumer", "Generate")["id"]
    last_consumer = _task(client, project, "Last historical consumer", "Generate")["id"]
    relative = result.video_url.removeprefix(f"/media/{project}/")
    with container.generation_service.uow_factory() as uow:
        source_job = uow.jobs.list_by_task(task)[0]
        uow.jobs.add(replace(
            source_job, id="legacy-consumer", task_id=consumer,
            context_snapshot={"media": [{"projectRelativePath": relative}]},
        ))
        uow.jobs.add(replace(
            source_job, id="last-legacy-consumer", task_id=last_consumer,
            context_snapshot={"media": [{"projectRelativePath": relative}]},
        ))
    container.lifecycle_service.transition_tasks(project, [task], "trash")
    container.permanent_delete_service.purge_tasks(project, [task], archive_results=False)
    with container.generation_service.uow_factory() as uow:
        assert uow.results.get(result.id) is None
        assert uow.jobs.get("legacy-consumer").context_snapshot == {
            "media": [{"projectRelativePath": relative}],
        }
    assert container.storage.resolve(project, relative).read_bytes() == b"fake-video-bytes"
    container.lifecycle_service.transition_tasks(project, [consumer], "trash")
    container.permanent_delete_service.purge_tasks(project, [consumer], archive_results=False)
    with container.generation_service.uow_factory() as uow:
        reference = uow.files.get_reference("project", project, "result", result.id, "output")
        assert reference is not None
    assert container.storage.resolve(project, relative).read_bytes() == b"fake-video-bytes"
    container.lifecycle_service.transition_tasks(project, [last_consumer], "trash")
    container.permanent_delete_service.purge_tasks(project, [last_consumer], archive_results=False)
    with container.generation_service.uow_factory() as uow:
        assert uow.files.get_reference("project", project, "result", result.id, "output") is None
