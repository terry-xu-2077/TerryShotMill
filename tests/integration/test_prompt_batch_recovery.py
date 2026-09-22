from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace

from shotmill.domain.application_settings import PromptSystemSettings
from shotmill.domain.enums import JobStatus
from shotmill.errors import ShotMillError
from shotmill.providers.prompt_ai.configurable import ConfigurablePromptAIProvider
from test_batch_review_api import _project, _task


class HeldQueue:
    def __init__(self):
        self.jobs: list[str] = []

    async def enqueue(self, job_id: str):
        self.jobs.append(job_id)


def _setup(client, count=3):
    project = _project(client)
    tasks = [_task(client, project["id"], f"Task {i}", f"Action {i}") for i in range(count)]
    service = client.app.state.container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    response = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches",
        json={"taskIds": [task["id"] for task in tasks]},
    )
    assert response.status_code == 202, response.text
    return project, service, queue, response.json()


def test_cancel_only_queued_items_and_keep_running_result(client, providers):
    project, service, queue, batch = _setup(client)
    provider = providers[0]
    original = provider.enhance

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def held(request):
            entered.set()
            await release.wait()
            return await original(request)

        provider.enhance = held
        running = asyncio.create_task(service._execute_prompt_job(queue.jobs[0]))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            result = await service.cancel_prompt_batch(project["id"], batch["batchId"])
            assert [item.state for item in result.items] == ["running", "cancelled", "cancelled"]
            # Repeat cancellation is harmless and cannot cancel the executing inference.
            again = await service.cancel_prompt_batch(project["id"], batch["batchId"])
            assert again == result
        finally:
            release.set()
            await running
            provider.enhance = original
        for job_id in queue.jobs[1:]:
            assert (await service._execute_prompt_job(job_id)).state == "skipped"
        service.refresh_prompt_batch(batch["batchId"])

    client.portal.call(scenario)
    assert len(provider.requests) == 1
    response = client.get(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches/{batch['batchId']}"
    )
    assert response.json()["state"] == "partial"
    with service.uow_factory() as uow:
        saved = uow.prompt_batches.get(batch["batchId"])
        assert (saved.completed_count, saved.cancelled_count, saved.running_count) == (1, 2, 0)
        finished_at = saved.finished_at
    service.refresh_prompt_batch(batch["batchId"])
    with service.uow_factory() as uow:
        assert uow.prompt_batches.get(batch["batchId"]).finished_at == finished_at


def test_retry_failed_creates_new_attempt_with_original_snapshots(client, providers):
    project, service, queue, batch = _setup(client, count=2)
    original = providers[0].enhance

    async def fail(request):
        raise ShotMillError("INJECTED_FAILURE", "temporary failure", 503)

    providers[0].enhance = fail
    client.portal.call(service._execute_prompt_job, queue.jobs[0])
    providers[0].enhance = original
    client.portal.call(service._execute_prompt_job, queue.jobs[1])
    service.refresh_prompt_batch(batch["batchId"])
    with service.uow_factory() as uow:
        failed = deepcopy(uow.prompt_jobs.get(queue.jobs[0]))
    response = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches/{batch['batchId']}/retry-failed"
    )
    assert response.status_code == 202, response.text
    retried = response.json()
    assert retried["batchId"] != batch["batchId"]
    assert [item["taskId"] for item in retried["items"]] == [failed.task_id]
    with service.uow_factory() as uow:
        attempt = uow.prompt_jobs.list_by_batch(retried["batchId"])[0]
        assert attempt.id != failed.id
        assert attempt.source_snapshot == failed.source_snapshot
        assert attempt.context_snapshot == failed.context_snapshot
        assert attempt.provider_profile_snapshot == failed.provider_profile_snapshot
        assert attempt.status == JobStatus.QUEUED
        assert uow.prompt_jobs.get(failed.id) == failed
    # A duplicate click cannot enqueue another inference for the same active task.
    repeated = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches/{batch['batchId']}/retry-failed"
    )
    assert repeated.status_code == 409
    assert len(queue.jobs) == 3
    client.portal.call(service._execute_prompt_job, attempt.id)
    service.refresh_prompt_batch(retried["batchId"])
    with service.uow_factory() as uow:
        assert uow.prompt_jobs.get(attempt.id).status == JobStatus.COMPLETED
        assert uow.prompt_jobs.get(failed.id) == failed


def test_cancel_endpoint_checks_project_and_survives_queue_restart(client, providers):
    project, service, queue, batch = _setup(client)
    other = _project(client)
    for action in ("cancel", "retry-failed"):
        response = client.post(
            f"/api/v1/projects/{other['id']}/prompt-enhancement-batches/{batch['batchId']}/{action}"
        )
        assert response.status_code == 404
    response = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches/{batch['batchId']}/cancel"
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "cancelled"
    actual_queue = client.app.state.container.prompt_enhancement_queue

    async def restart():
        await actual_queue.stop()
        await actual_queue.start()
        await actual_queue._queue.join()

    client.portal.call(restart)
    assert providers[0].requests == []
    with service.uow_factory() as uow:
        assert uow.prompt_jobs.list_active() == []
        assert all(uow.prompt_jobs.get(job).status == JobStatus.CANCELLED for job in queue.jobs)
    retry = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches/{batch['batchId']}/retry-failed"
    )
    assert retry.status_code == 409


def test_workspace_runtime_keeps_failures_and_cancelled_items_after_reload(client, providers):
    project, service, queue, batch = _setup(client, count=2)

    async def fail(request):
        raise ShotMillError("PROVIDER_UNAVAILABLE", "unavailable", 503)

    providers[0].enhance = fail
    client.portal.call(service._execute_prompt_job, queue.jobs[0])
    client.portal.call(service.cancel_prompt_batch, project["id"], batch["batchId"])
    # Separate requests/UoWs read the database, not an in-memory runtime response.
    for _ in range(2):
        response = client.get(f"/api/v1/projects/{project['id']}/workspace")
        assert response.status_code == 200, response.text
        runtime = response.json()["runtime"]
        persisted = runtime["promptBatches"][0]
        assert persisted["id"] == batch["batchId"]
        assert persisted["failedCount"] == 1
        assert persisted["cancelledCount"] == 1
        assert persisted["queuedCount"] == 0
        assert persisted["items"][0]["title"] == "Task 0"
        assert persisted["items"][0]["elapsedSeconds"] >= 0
        assert persisted["items"][0]["error"] == "增强服务不可用，请检查连接后重试。"
        assert "sourceSnapshot" not in persisted["items"][0]
        task = response.json()["tasks"][0]
        assert task["timing"]["promptSeconds"] >= 0
        assert task["timing"]["promptQueueSeconds"] >= 0
        direct = client.app.state.container.workspace_query.task_summary(project["id"], task["id"])
        assert direct.timing.prompt_seconds == task["timing"]["promptSeconds"]


def _enhance_input():
    return {
        "target": "minimax-h3", "userPrompt": "当前编辑器中的描述", "media": [],
        "context": {"includeProjectBackground": False, "includePreviousTaskSummary": False},
        "generation": {"durationSeconds": 6, "mode": "全能参考", "contextMode": "不承接"},
    }


def test_single_enhancement_cannot_duplicate_an_active_batch_task(client, providers):
    project, _, _, batch = _setup(client, count=1)
    response = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{batch['items'][0]['taskId']}/prompt-enhancements",
        json=_enhance_input(),
    )
    assert response.status_code == 409
    assert providers[0].requests == []


def test_failed_single_enhancement_is_timed_and_retry_keeps_its_input(client, providers):
    project = _project(client)
    task = _task(client, project["id"], "单项增强", "保存的描述")
    provider = providers[0]
    original = provider.enhance

    async def fail(request):
        raise ShotMillError("PROVIDER_UNAVAILABLE", "temporary failure", 503)

    provider.enhance = fail
    response = client.post(
        f"/api/v1/projects/{project['id']}/tasks/{task['id']}/prompt-enhancements",
        json=_enhance_input(),
    )
    assert response.status_code == 503
    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    assert workspace["tasks"][0]["timing"]["promptSeconds"] >= 0
    batch = workspace["runtime"]["promptBatches"][0]
    assert batch["failedCount"] == 1
    service = client.app.state.container.batch_production_service
    queue = HeldQueue()
    service.attach_queue(queue)
    provider.enhance = original
    retried = client.post(
        f"/api/v1/projects/{project['id']}/prompt-enhancement-batches/{batch['id']}/retry-failed"
    )
    assert retried.status_code == 202
    client.portal.call(service._execute_prompt_job, queue.jobs[0])
    assert "当前编辑器中的描述" in provider.requests[-1].user_text
    editor = client.get(f"/api/v1/projects/{project['id']}/tasks/{task['id']}/editor").json()
    assert editor["promptSource"] == "user"


def test_twenty_queued_tasks_restore_with_frozen_configuration_and_empty_context(client, providers):
    project = _project(client)
    project_id = project["id"]
    tasks = [_task(client, project_id, f"Task {i}", f"Action {i}") for i in range(20)]
    service = client.app.state.container.batch_production_service
    service.attach_queue(HeldQueue())
    system = PromptSystemSettings(system_prompt="submitted rules")
    provider = providers[0]
    service.prompt_service.provider = ConfigurablePromptAIProvider(
        provider, provider, lambda: system
    )
    client.patch(f"/api/v1/projects/{project_id}", json={"description": ""})
    submitted = client.post(
        f"/api/v1/projects/{project_id}/prompt-enhancement-batches",
        json={
            "taskIds": [task["id"] for task in reversed(tasks)],
            "includeProjectBackground": True,
        },
    )
    assert submitted.status_code == 202, submitted.text
    batch_id = submitted.json()["batchId"]
    assert [item["taskId"] for item in submitted.json()["items"]] == [task["id"] for task in tasks]
    duplicate = client.post(
        f"/api/v1/projects/{project_id}/prompt-enhancement-batches",
        json={"taskIds": [task["id"] for task in tasks]},
    )
    assert all(item["state"] == "skipped" for item in duplicate.json()["items"])
    # Both mutable settings and optional context change while the queue is stopped.
    system = replace(system, provider_mode="api", system_prompt="later rules")
    client.patch(f"/api/v1/projects/{project_id}", json={"description": "LATER BACKGROUND"})
    actual_queue = client.app.state.container.prompt_enhancement_queue

    async def restart():
        await actual_queue.stop()
        await actual_queue.start()
        await actual_queue._queue.join()

    client.portal.call(restart)
    assert len(provider.requests) == 20
    assert all(request.system_prompt == "submitted rules" for request in provider.requests)
    assert all("LATER BACKGROUND" not in request.user_text for request in provider.requests)
    with service.uow_factory() as uow:
        batch = uow.prompt_batches.get(batch_id)
        assert batch.completed_count == 20
        assert batch.status == "completed"
        assert [job.task_id for job in uow.prompt_jobs.list_by_batch(batch_id)] == [
            task["id"] for task in tasks
        ]
        assert all(
            uow.prompt_jobs.list_by_batch(batch_id)[i].source_snapshot["userPrompt"]
            == f"Action {i}"
            for i in range(20)
        )
