import pytest
from shotmill.application.project_import_media import bind_project_import_media
from shotmill.application.project_import_preflight import preflight_project_import
from shotmill.application.project_transfer_identity import remap_project_identity
from test_batch_review_api import _project
from test_project_export_service import exporter


@pytest.mark.parametrize("rollback", [False, True])
def test_import_media_has_independent_owners_without_rewriting_existing_content(
    client, monkeypatch, rollback,
):
    container = client.app.state.container
    project = _project(client)["id"]
    asset = container.asset_service.import_bytes(project, "source.png", b"same")
    original_path = container.storage.resolve(project, asset.project_relative_path)

    def forbid(*args, **kwargs):
        pytest.fail("Existing global content should not be rewritten")

    with exporter(container).prepare(project) as archive:
        with archive.open("rb") as stream, preflight_project_import(stream) as package:
            identity = remap_project_identity(package.source)
            monkeypatch.setattr(container.file_library.storage, "put", forbid)

            def publish():
                with container.generation_service.uow_factory() as uow:
                    uow.reserve_write()
                    mapped = bind_project_import_media(uow, container.file_library, identity,
                                                       package.files)
                    uow.projects.add(mapped.project)
                    for imported in mapped.assets:
                        uow.assets.add(imported)
                    if rollback:
                        raise RuntimeError("Injected save failure")
                    return mapped

            if rollback:
                with pytest.raises(RuntimeError):
                    publish()
            else:
                mapped = publish()
                imported = mapped.assets[0]
                assert imported.id != asset.id
                assert imported.project_relative_path == f"shared/asset/{imported.id}/content"
                imported_path = container.storage.resolve(
                    mapped.project.id, imported.project_relative_path,
                )
                assert imported_path == original_path
    with container.generation_service.uow_factory() as uow:
        references = uow.files.references(asset.hash)
        assert len(references) == (1 if rollback else 2)
        assert (uow.projects.get(identity.source.project.id) is None) == rollback
    assert original_path.read_bytes() == b"same"
