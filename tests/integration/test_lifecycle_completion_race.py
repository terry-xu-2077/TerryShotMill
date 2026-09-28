import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from shotmill.domain.enums import JobStatus
from shotmill.domain.providers import GeneratedOutput, VideoGenerationResponse
from shotmill.persistence.repositories.history import (
    SqlAlchemyPromptRevisionRepository,
    SqlAlchemyResultRepository,
)
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


@pytest.mark.parametrize("target", ["project", "task"])
@pytest.mark.parametrize("phase", ["remote", "file", "result", "committing"])
def test_completion_boundary_cannot_lose_results_to_deletion(
    client, providers, monkeypatch, target, phase,
):
    project = _project(client)["id"]
    task = _task(client, project, "完成与删除交错", "两个生成产出")["id"]
    container = client.app.state.container
    generation = container.generation_service
    generation.attach_queue(HeldQueue())
    entered, release = Event(), Event()

    def hold():
        entered.set()
        assert release.wait(10), "completion test did not release generation"

    async def generate(request):
        if phase == "remote":
            await asyncio.to_thread(hold)
        return VideoGenerationResponse("remote", (
            GeneratedOutput("clip.mp4", b"first", "video/mp4"),
            GeneratedOutput("clip.mp4", b"second", "video/mp4"),
        ))

    monkeypatch.setattr(providers[1], "generate", generate)
    if phase == "file":
        storage = generation.result_collector.library.storage
        original = storage.put

        def write(*args, **kwargs):
            value = original(*args, **kwargs)
            hold()
            return value

        monkeypatch.setattr(storage, "put", write)
    elif phase in {"result", "committing"}:
        original = SqlAlchemyResultRepository.add

        def add(self, result):
            if phase == "committing":
                value = original(self, result)
                self.session.flush()
                hold()
                return value
            hold()
            return original(self, result)

        monkeypatch.setattr(SqlAlchemyResultRepository, "add", add)
    base = f"/api/v1/projects/{project}"
    submitted = client.post(f"{base}/tasks/{task}/generation", json={})
    assert submitted.status_code == 202
    job_id = submitted.json()["id"]
    lifecycle_path = f"{base}/lifecycle" if target == "project" else f"{base}/tasks/lifecycle"
    trash = {"action": "trash"}
    purge = {"confirmed": True}
    purge_path = f"{base}/permanent-delete"
    if target == "task":
        trash["taskIds"] = [task]
        purge["taskIds"] = [task]
        purge_path = f"{base}/tasks/permanent-delete"
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(lambda: asyncio.run(generation.execute(job_id)))
        try:
            assert entered.wait(5)
            assert generation.get_job(job_id).status == JobStatus.RUNNING
            if phase in {"result", "committing"}:
                # File references and Result rows share the reserved write
                # transaction, including the phase before Result.add flushes.
                deleting = pool.submit(lambda: client.post(lifecycle_path, json=trash))
                with pytest.raises(TimeoutError):
                    deleting.result(timeout=0.3)
            else:
                response = client.post(lifecycle_path, json=trash)
                assert response.status_code == 409, response.text
                assert "TASK_BUSY" in response.text
                response = client.post(purge_path, json=purge)
                assert response.status_code == 409, response.text
                with generation.uow_factory() as uow:
                    assert uow.tasks.get(task) is not None
                    assert uow.cleanup.list() == []
        finally:
            release.set()
        running.result(timeout=10)
        if phase in {"result", "committing"}:
            assert deleting.result(timeout=10).status_code == 200
    assert generation.get_job(job_id).status == JobStatus.COMPLETED
    assert client.post(lifecycle_path, json=trash).status_code == 200
    response = client.post(purge_path, json=purge)
    assert response.status_code == 200, response.text
    assert response.json()["archivedResultCount"] == 2
    records = container.permanent_delete_service.archive.list()
    assert len(records) == 2
    archive = container.permanent_delete_service.archive
    with generation.uow_factory() as uow:
        assert all(archive.verify_in(uow, record) for record in records)
        outputs = {
            archive.file_path_in(uow, record, item).read_bytes()
            for record in records for item in record.files if item["role"] == "output"
        }
        assert outputs == {b"first", b"second"}
        assert uow.tasks.get(task) is None
        assert uow.jobs.get(job_id) is None


@pytest.mark.parametrize("target", ["project", "task"])
@pytest.mark.parametrize("phase", ["provider", "revision"])
def test_running_prompt_cancel_does_not_unlock_deletion_before_completion(
    client, providers, monkeypatch, target, phase,
):
    project = _project(client)["id"]
    task = _task(client, project, "增强完成与删除交错", "原提示词")["id"]
    service = client.app.state.container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    base = f"/api/v1/projects/{project}"
    response = client.post(f"{base}/prompt-enhancement-batches", json={"taskIds": [task]})
    assert response.status_code == 202
    batch_id = response.json()["batchId"]
    entered, release = Event(), Event()

    def hold():
        entered.set()
        assert release.wait(10)

    if phase == "provider":
        original = providers[0].enhance

        async def enhance(request):
            await asyncio.to_thread(hold)
            return await original(request)

        monkeypatch.setattr(providers[0], "enhance", enhance)
    else:
        original = SqlAlchemyPromptRevisionRepository.add

        def add(self, revision):
            hold()
            return original(self, revision)

        monkeypatch.setattr(SqlAlchemyPromptRevisionRepository, "add", add)
    path = f"{base}/lifecycle" if target == "project" else f"{base}/tasks/lifecycle"
    payload = {"action": "trash"}
    if target == "task":
        payload["taskIds"] = [task]
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(lambda: asyncio.run(service._execute_prompt_job(queue.jobs[0])))
        try:
            assert entered.wait(5)
            cancelled = client.post(f"{base}/prompt-enhancement-batches/{batch_id}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["items"][0]["state"] == "running"
            denied = client.post(path, json=payload)
            assert denied.status_code == 409
            assert "TASK_BUSY" in denied.text
        finally:
            release.set()
        assert running.result(timeout=10).state == "completed"
    with service.uow_factory() as uow:
        assert len(uow.prompt_revisions.list_by_task(task)) == 1
        assert uow.tasks.get(task).ai_prompt
    assert client.post(path, json=payload).status_code == 200
    purge_path = f"{base}/permanent-delete" if target == "project" else (
        f"{base}/tasks/permanent-delete"
    )
    purge_payload = {"confirmed": True}
    if target == "task":
        purge_payload["taskIds"] = [task]
    assert client.post(purge_path, json=purge_payload).status_code == 200
    with service.uow_factory() as uow:
        assert uow.tasks.get(task) is None
        assert uow.prompt_jobs.get(queue.jobs[0]) is None


@pytest.mark.parametrize("target", ["project", "task"])
def test_cancelled_video_deleted_before_late_claim_never_executes(client, providers, target):
    project = _project(client)["id"]
    task = _task(client, project, "取消后永久删除", "不能迟到执行")["id"]
    generation = client.app.state.container.generation_service
    generation.attach_queue(HeldQueue())
    base = f"/api/v1/projects/{project}"
    submitted = client.post(f"{base}/tasks/{task}/generation", json={})
    assert submitted.status_code == 202
    job = submitted.json()["id"]
    response = client.post(f"{base}/video-generation-queue/cancel", json={"jobIds": [job]})
    assert response.status_code == 200
    assert response.json()["cancelledJobIds"] == [job]
    path = base if target == "project" else f"{base}/tasks"
    selection = {} if target == "project" else {"taskIds": [task]}
    trashed = client.post(f"{path}/lifecycle", json={**selection, "action": "trash"})
    assert trashed.status_code == 200
    assert client.post(f"{path}/permanent-delete", json={
        **selection, "confirmed": True,
    }).status_code == 200
    client.portal.call(generation.execute, job)
    assert providers[1].requests == []
    with generation.uow_factory() as uow:
        assert uow.tasks.get(task) is None
        assert uow.jobs.get(job) is None
        assert uow.results.list_by_task(task) == []
