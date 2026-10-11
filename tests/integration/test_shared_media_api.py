import pytest
from shotmill.domain.entities import Asset
from shotmill.persistence.repositories.project_asset import SqlAlchemyAssetRepository
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from test_batch_review_api import _project


def upload(client, project, filename="frame.png", content=b"image-content"):
    response = client.post(
        f"/api/v1/projects/{project}/assets",
        files={"file": (filename, content, "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_actual_uploads_share_one_object_and_serve_logical_mime_and_ranges(client):
    container = client.app.state.container
    first, second = _project(client)["id"], _project(client)["id"]
    a, b = upload(client, first), upload(client, second, "renamed.png")
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        asset_a, asset_b = uow.assets.get(a["id"]), uow.assets.get(b["id"])
        assert asset_a.hash == asset_b.hash
        assert len(uow.files.references(asset_a.hash)) == 2
    url_a = container.storage.media_url(first, asset_a.project_relative_path)
    url_b = container.storage.media_url(second, asset_b.project_relative_path)
    assert url_a != url_b
    assert client.get(url_a).content == b"image-content"
    assert client.head(url_a).headers["content-type"] == "image/png"
    ranged = client.get(url_b, headers={"Range": "bytes=0-4"})
    assert ranged.status_code == 206
    assert ranged.content == b"image"
    assert client.get(url_a.replace(first, second)).status_code == 404
    assert len(list(container.settings.files_root.glob("objects/*/*"))) == 1
    assert client.get(f"/files/objects/{asset_a.hash[:2]}/{asset_a.hash}").status_code == 404

    container.removal_service.remove_project(first)
    assert client.get(url_a).status_code == 404
    assert client.get(url_b).content == b"image-content"


def test_failed_asset_save_does_not_remove_another_projects_shared_bytes(client, monkeypatch):
    container = client.app.state.container
    first, second = _project(client)["id"], _project(client)["id"]
    saved = upload(client, first)
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        original = uow.assets.get(saved["id"])

    def fail(*args):
        raise RuntimeError("database save failed")

    monkeypatch.setattr(SqlAlchemyAssetRepository, "add", fail)
    with pytest.raises(RuntimeError, match="database save failed"):
        container.asset_service.import_bytes(second, "again.png", b"image-content")
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        assert uow.assets.list_by_project(second) == []
        assert len(uow.files.references(original.hash)) == 1
    url = container.storage.media_url(first, original.project_relative_path)
    assert client.get(url).content == b"image-content"


def test_legacy_assets_remain_readable_without_being_moved(client):
    container = client.app.state.container
    project = _project(client)["id"]
    relative, checksum = container.storage.write_asset(project, "legacy", "old.png", b"legacy")
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        uow.assets.add(Asset("legacy", project, "Old", "old.png", relative, "image", hash=checksum))
        assert uow.files.get(checksum) is None
    assert client.get(container.storage.media_url(project, relative)).content == b"legacy"
    assert container.storage.resolve(project, relative).read_bytes() == b"legacy"


def test_missing_shared_bytes_still_return_http_404(client):
    container = client.app.state.container
    project = _project(client)["id"]
    saved = upload(client, project)
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        asset = uow.assets.get(saved["id"])
    path = container.storage.resolve(project, asset.project_relative_path)
    path.unlink()
    assert container.storage.resolve(project, asset.project_relative_path) == path
    url = container.storage.media_url(project, asset.project_relative_path)
    assert client.get(url).status_code == 404
