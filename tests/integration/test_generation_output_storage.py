from io import BytesIO

import pytest
from shotmill.domain.enums import JobStatus
from shotmill.domain.providers import GeneratedOutput, VideoGenerationResponse
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


@pytest.mark.parametrize("save_fails", [False, True])
def test_generation_closes_streams_after_save_or_failure(
    client, providers, monkeypatch, save_fails
):
    project = _project(client)["id"]
    task = _task(client, project, "文件流结果", "保存结果")["id"]
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    streams = [BytesIO(b"first-video"), BytesIO(b"second-video")]

    async def generate(request):
        return VideoGenerationResponse(provider_job_id="remote", outputs=tuple(
            GeneratedOutput("clip.mp4", stream, "video/mp4") for stream in streams
        ))

    def fail_save(*args):
        raise OSError("disk full")

    monkeypatch.setattr(providers[1], "generate", generate)
    if save_fails:
        monkeypatch.setattr(service.result_collector.library.storage, "put", fail_save)
    response = client.post(f"/api/v1/projects/{project}/tasks/{task}/generation", json={})
    assert response.status_code == 202
    job_id = response.json()["id"]
    client.portal.call(service.execute, job_id)
    assert all(stream.closed for stream in streams)
    assert service.get_job(job_id).status == (
        JobStatus.FAILED if save_fails else JobStatus.COMPLETED
    )
    with service.uow_factory() as uow:
        assert uow.results.count_by_task(task) == (0 if save_fails else 2)


def test_generation_keeps_both_same_named_outputs(client, providers, monkeypatch):
    project = _project(client)["id"]
    task = _task(client, project, "同名结果", "生成两个版本")["id"]
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())

    async def generate(request):
        return VideoGenerationResponse(provider_job_id="remote", outputs=[
            GeneratedOutput("clip.mp4", b"first-video", "video/mp4"),
            GeneratedOutput("clip.mp4", b"second-video", "video/mp4"),
        ])

    monkeypatch.setattr(providers[1], "generate", generate)
    response = client.post(
        f"/api/v1/projects/{project}/tasks/{task}/generation", json={}
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    client.portal.call(service.execute, job_id)
    assert service.get_job(job_id).status == JobStatus.COMPLETED
    with service.uow_factory() as uow:
        results = uow.results.list_by_task(task)
    assert len(results) == 2
    assert len({result.video_url for result in results}) == 2
    assert {client.get(result.video_url).content for result in results} == {
        b"first-video", b"second-video",
    }


def test_shared_generated_result_remains_importable_after_source_removal(client):
    from shotmill.application.asset_import_service import ImportSelection

    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    source, target = _project(client)["id"], _project(client)["id"]
    task = _task(client, source, "Source", "Generate")["id"]
    for _ in range(2):
        submitted = client.post(f"/api/v1/projects/{source}/tasks/{task}/generation", json={})
        assert submitted.status_code == 202
        client.portal.call(service.execute, submitted.json()["id"])
    with service.uow_factory() as uow:
        results = uow.results.list_by_task(task)
        assert len(results) == 2
        assert len({result.job_id for result in results}) == 2
        assert results[0].video_url != results[1].video_url
    imported = container.asset_import_service.import_sources(
        target, [ImportSelection("result", results[0].id)],
    )[0]
    assert imported.original_filename == "result.mp4"
    source_output = container.storage.resolve_read(
        source, results[0].video_url.removeprefix(f"/media/{source}/"),
    )
    container.removal_service.remove_project(source)
    url = container.storage.media_url(target, imported.project_relative_path)
    assert client.get(url).content == b"fake-video-bytes"
    assert source_output.read_bytes() == b"fake-video-bytes"


def test_result_database_failure_rolls_back_references_but_keeps_shared_asset(client, monkeypatch):
    from shotmill.persistence.repositories.history import SqlAlchemyResultRepository

    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    source, target = _project(client)["id"], _project(client)["id"]
    asset = container.asset_service.import_bytes(source, "existing.mp4", b"fake-video-bytes")
    task = _task(client, target, "Failure", "Generate")["id"]

    def fail(*args):
        raise RuntimeError("result save failed")

    monkeypatch.setattr(SqlAlchemyResultRepository, "add", fail)
    submitted = client.post(f"/api/v1/projects/{target}/tasks/{task}/generation", json={})
    assert submitted.status_code == 202
    job_id = submitted.json()["id"]
    client.portal.call(service.execute, job_id)
    assert service.get_job(job_id).status == JobStatus.FAILED
    with service.uow_factory() as uow:
        assert uow.results.list_by_task(task) == []
        refs = uow.files.references(asset.hash)
        assert len(refs) == 1 and refs[0].owner_id == asset.id
    url = container.storage.media_url(source, asset.project_relative_path)
    assert client.get(url).content == b"fake-video-bytes"
