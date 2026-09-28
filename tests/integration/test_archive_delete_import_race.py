from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from shotmill.application.asset_import_service import ImportSelection
from shotmill.errors import NotFoundError
from shotmill.persistence.repositories.archive import SqlAlchemyArchivedResultRepository
from test_batch_review_api import _project
from test_shared_result_archive import generated


@pytest.mark.parametrize("delete_first", [False, True])
def test_archive_delete_and_import_serialize_without_partial_assets(
    client, monkeypatch, delete_first,
):
    container, project, task, _ = generated(client)
    archive = container.result_archive_service.archive_tasks(project, [task])[0]
    target = _project(client)["id"]
    entered, release, second_started = Event(), Event(), Event()
    original = SqlAlchemyArchivedResultRepository.get

    def hold_first_read(repository, archive_id):
        record = original(repository, archive_id)
        if archive_id == archive.id and not entered.is_set():
            entered.set()
            assert release.wait(5), "first archive transaction was not released"
        return record

    monkeypatch.setattr(SqlAlchemyArchivedResultRepository, "get", hold_first_read)

    def delete():
        return container.result_archive_service.delete(archive.id)

    def import_asset():
        return container.asset_import_service.import_sources(
            target, [ImportSelection("archive", archive.id)],
        )

    def second_operation():
        second_started.set()
        return import_asset() if delete_first else delete()

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(delete if delete_first else import_asset)
        assert entered.wait(5)
        second = workers.submit(second_operation)
        try:
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.3)
        finally:
            release.set()
        first.result(timeout=5)
        if delete_first:
            with pytest.raises(NotFoundError):
                second.result(timeout=5)
        else:
            second.result(timeout=5)

    with container.result_archive_service.uow_factory() as uow:
        assert uow.archived_results.get(archive.id) is None
        assets = uow.assets.list_by_project(target)
        assert len(assets) == (0 if delete_first else 1)
        references = uow.files.references(archive.files[0]["sha256"])
        assert not any(ref.scope_kind == "archive" and ref.scope_id == archive.id
                       for ref in references)
        assert any(ref.scope_kind == "project" and ref.scope_id == target
                   for ref in references) == (not delete_first)
    if assets:
        path = container.storage.resolve_read(target, assets[0].project_relative_path)
        assert path.read_bytes() == b"fake-video-bytes"
