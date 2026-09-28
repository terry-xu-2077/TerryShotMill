from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO

import pytest
from alembic import command
from shotmill.application.file_library import FileLibrary
from shotmill.domain.files import FileReference
from shotmill.media.file_storage import FileStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.migrations import alembic_config, upgrade_database
from shotmill.persistence.models import StoredFileModel
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def library(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'files.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    try:
        yield FileLibrary(FileStorage(tmp_path / "files")), lambda: SqlAlchemyUnitOfWork(sessions)
    finally:
        engine.dispose()


def import_file(service, uow, project="p", owner="a", data=b"shared", kind="asset"):
    return service.import_file(
        uow, BytesIO(data), scope_kind="project", scope_id=project,
        owner_kind=kind, owner_id=owner, slot="content",
    )


def test_two_projects_share_bytes_but_have_independent_owners(library):
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        first = import_file(service, uow)
        second = import_file(service, uow, project="other", owner="b")
        assert first == second
    with factory() as uow:
        assert len(uow.files.references(first.sha256)) == 2
        assert uow.files.unreferenced() == []
        uow.files.release_owner("project", "p", "asset", "a")
    with factory() as uow:
        refs = uow.files.references(first.sha256)
        assert len(refs) == 1 and refs[0].scope_id == "other"
        assert service.resolve(uow, refs[0]).read_bytes() == b"shared"
        assert uow.files.unreferenced() == []
    assert len(list(service.storage.managed.root.glob("objects/*/*"))) == 1


def test_history_and_archive_references_prevent_candidate_collection(library):
    service, factory = library
    with factory() as uow:
        uow.reserve_write()
        file = import_file(service, uow)
        import_file(service, uow, owner="job", kind="job")
        archive = FileReference("archive", "record", "result", "r", "output", file.sha256)
        uow.files.bind(archive)
        uow.files.release_owner("project", "p", "asset", "a")
        assert uow.files.unreferenced() == []
        uow.files.release_owner("project", "p", "job", "job")
        assert uow.files.references(file.sha256) == [archive]
        assert uow.files.unreferenced() == []
        uow.files.release_owner("archive", "record", "result", "r")
        assert uow.files.unreferenced() == [file]
    # A diagnostic candidate is not an automatic destructive operation.
    assert service.storage.resolve(file).read_bytes() == b"shared"


def test_rollback_does_not_remove_file_owned_by_another_project(library):
    service, factory = library
    with factory() as uow:
        file = import_file(service, uow)
    with pytest.raises(RuntimeError), factory() as uow:
        uow.reserve_write()
        import_file(service, uow, project="other")
        raise RuntimeError("business save failed")
    with factory() as uow:
        assert len(uow.files.references(file.sha256)) == 1
        assert uow.files.references(file.sha256)[0].scope_id == "p"
        assert service.storage.resolve(file).read_bytes() == b"shared"


def test_rollback_new_object_leaves_no_visible_reference_and_retry_reuses_bytes(library):
    service, factory = library
    with pytest.raises(RuntimeError), factory() as uow:
        file = import_file(service, uow)
        raise RuntimeError("save failed")
    with factory() as uow:
        assert uow.files.get(file.sha256) is None
        assert uow.files.references(file.sha256) == []
        assert import_file(service, uow) == file
    assert len(list(service.storage.managed.root.glob("objects/*/*"))) == 1


def test_reference_idempotency_and_immutable_rebind(library):
    service, factory = library
    with factory() as uow:
        first = import_file(service, uow)
        assert import_file(service, uow) == first
        assert len(uow.files.references(first.sha256)) == 1
    with pytest.raises(ValueError, match="immutable"), factory() as uow:
        import_file(service, uow, data=b"different")
    with factory() as uow:
        ref = uow.files.references(first.sha256)[0]
        assert service.resolve(uow, ref).read_bytes() == b"shared"
        with pytest.raises(ValueError, match="logical owner"):
            service.resolve(uow, replace(ref, scope_id="not-owner"))


def test_database_prevents_removing_a_referenced_object(library):
    service, factory = library
    with factory() as uow:
        file = import_file(service, uow)
    with pytest.raises(IntegrityError), factory() as uow:
        uow.session.execute(delete(StoredFileModel).where(StoredFileModel.sha256 == file.sha256))
    with factory() as uow:
        assert uow.files.get(file.sha256) == file


def test_registration_rejects_metadata_conflicts_and_missing_file_references(library):
    service, factory = library
    with factory() as uow:
        file = import_file(service, uow)
        with pytest.raises(ValueError, match="Conflicting"):
            uow.files.register(replace(file, size=file.size + 1))
        with pytest.raises(ValueError, match="unregistered"):
            uow.files.bind(FileReference("project", "p", "asset", "b", "content", "0" * 64))


def test_schema_upgrade_preserves_projects_and_legacy_files(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    command.upgrade(alembic_config(url), "0012")
    engine = create_database_engine(url)
    factory = create_session_factory(engine)
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO projects
                (id, title, description, use_description_for_ai_prompt, created_at, updated_at)
                VALUES ('legacy', 'Existing', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """))
        media = tmp_path / "legacy.mp4"
        media.write_bytes(b"keep")
        upgrade_database(url)
        with SqlAlchemyUnitOfWork(factory) as uow:
            assert uow.projects.get("legacy").title == "Existing"
            assert uow.files.unreferenced() == []
        assert media.read_bytes() == b"keep"
    finally:
        engine.dispose()


def test_concurrent_transactions_reuse_one_object_and_retain_every_owner(library):
    service, factory = library

    def write(index):
        with factory() as uow:
            uow.reserve_write()
            return import_file(service, uow, project=f"project-{index}")

    with ThreadPoolExecutor(max_workers=4) as workers:
        files = list(workers.map(write, range(8)))
    assert len(set(files)) == 1
    with factory() as uow:
        assert len(uow.files.references(files[0].sha256)) == 8
    assert len(list(service.storage.managed.root.glob("objects/*/*"))) == 1


def test_release_is_scoped_even_when_owner_identifiers_match(library):
    service, factory = library
    with factory() as uow:
        file = import_file(service, uow)
        import_file(service, uow, project="other")
        archive_ref = FileReference("archive", "p", "asset", "a", "content", file.sha256)
        uow.files.bind(archive_ref)
        uow.files.release_owner("project", "p", "asset", "a")
        refs = uow.files.references(file.sha256)
        assert len(refs) == 2
        assert archive_ref in refs
        assert any(ref.scope_id == "other" for ref in refs)
