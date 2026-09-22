import asyncio
from copy import deepcopy

from shotmill.domain.enums import JobStatus, TaskState
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def _submit(client, project, task):
    response = client.post(f'/api/v1/projects/{project}/tasks/{task}/generation', json={})
    assert response.status_code == 202, response.text
    return response.json()['id']


def test_cancel_queued_video_api_is_scoped_idempotent_and_retains_results(client, providers):
    project = _project(client)['id']
    other = _project(client)['id']
    task = _task(client, project, '原有成片', '原始提示词')['id']
    foreign_task = _task(client, other, '其他项目', '其他提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    original = _submit(client, project, task)
    client.portal.call(service.execute, original)
    with service.uow_factory() as uow:
        primary = uow.tasks.get(task).primary_result_id
        history = deepcopy(uow.results.get(primary))
    queued = _submit(client, project, task)
    foreign = _submit(client, other, foreign_task)
    before = service.get_job(queued)
    endpoint = f'/api/v1/projects/{project}/video-generation-queue/cancel'
    rejected = client.post(endpoint, json={'jobIds': [queued, foreign]})
    assert rejected.status_code == 404
    assert service.get_job(queued) == before
    assert client.post(endpoint, json={'jobIds': [queued, 'missing']}).status_code == 404
    assert service.get_job(queued) == before
    response = client.post(endpoint, json={'jobIds': [queued, queued, original]})
    assert response.status_code == 200, response.text
    assert response.json() == {'cancelledJobIds': [queued]}
    cancelled = service.get_job(queued)
    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.started_at is None
    assert cancelled.completed_at is not None
    assert cancelled.params_snapshot == before.params_snapshot
    assert cancelled.final_prompt_snapshot == before.final_prompt_snapshot
    assert client.post(endpoint, json={'jobIds': [queued]}).json() == {'cancelledJobIds': []}
    assert service.get_job(queued) == cancelled
    client.portal.call(service.execute, queued)
    assert len(providers[1].requests) == 1
    assert service.get_job(foreign).status == JobStatus.QUEUED
    with service.uow_factory() as uow:
        current = uow.tasks.get(task)
        assert current.state == TaskState.COMPLETED
        assert current.primary_result_id == primary
        assert uow.results.get(primary) == history
        assert uow.results.count_by_task(task) == 1
    workspace = client.get(f'/api/v1/projects/{project}/workspace').json()
    item = next(j for j in workspace['runtime']['videoJobs'] if j['id'] == queued)
    assert item['state'] == 'cancelled'
    # Cancellation unlocks the task for editing; no immutable history is removed.
    editor = client.get(f'/api/v1/projects/{project}/tasks/{task}/editor').json()
    assert client.patch(f'/api/v1/projects/{project}/tasks/{task}', json=editor).status_code == 200


def test_scheduler_cancel_keeps_running_video_and_skips_cancelled_after_restart(client, providers):
    project = _project(client)['id']
    tasks = [_task(client, project, str(i), '内容')['id'] for i in range(3)]
    container = client.app.state.container
    service = container.generation_service
    service.attach_queue(HeldQueue())
    jobs = [_submit(client, project, task) for task in tasks]
    provider = providers[1]
    original = provider.generate

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def held(request):
            entered.set()
            await release.wait()
            return await original(request)

        provider.generate = held
        execution = asyncio.create_task(service.execute(jobs[0]))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            running = service.get_job(jobs[0])
            assert await service.cancel_queued(project, jobs) == jobs[1:]
            assert service.get_job(jobs[0]) == running
        finally:
            release.set()
            await execution
            provider.generate = original
        await container.generation_queue.stop()
        await container.generation_queue.start()
        await container.generation_queue._queue.join()
        for job in jobs[1:]:
            await service.execute(job)

    client.portal.call(scenario)
    assert len(provider.requests) == 1
    assert [service.get_job(job).status for job in jobs] == [
        JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.CANCELLED,
    ]
    with service.uow_factory() as uow:
        assert all(uow.tasks.get(task).state == TaskState.PROMPT_READY for task in tasks[1:])
