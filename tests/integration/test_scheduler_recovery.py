import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from shotmill.app import create_app
from shotmill.domain.entities import utcnow
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.errors import ProviderUnavailableError
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def _submit(client, project, task):
    response = client.post(f'/api/v1/projects/{project}/tasks/{task}/generation', json={})
    assert response.status_code == 202, response.text
    return response.json()['id']


def test_scheduler_deduplicates_concurrent_and_completed_video_deliveries(client, providers):
    project = _project(client)['id']
    task = _task(client, project, '镜头', '原始内容')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    provider = providers[1]
    original = provider.generate

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def held(request):
            entered.set()
            await release.wait()
            return await original(request)

        provider.generate = held
        first = asyncio.create_task(service.execute(job_id))
        deliveries = [first]
        try:
            await asyncio.wait_for(entered.wait(), 2)
            deliveries.append(asyncio.create_task(service.execute(job_id)))
            await asyncio.sleep(0)
        finally:
            release.set()
            await asyncio.gather(*deliveries)
            provider.generate = original
        before = service.get_job(job_id)
        await service.execute(job_id)
        assert service.get_job(job_id) == before

    client.portal.call(scenario)
    assert len(provider.requests) == 1
    with service.uow_factory() as uow:
        assert uow.results.count_by_task(task) == 1


def test_scheduler_recovers_twenty_video_jobs_in_order_with_partial_failure(client, providers):
    project = _project(client)['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    tasks = [_task(client, project, f'Task {i}', f'Frozen {i}')['id'] for i in range(20)]
    jobs = [_submit(client, project, task) for task in tasks]
    with service.uow_factory() as uow:
        changed = uow.tasks.get(tasks[0])
        changed.final_prompt = 'later content must not replace the snapshot'
        uow.tasks.update(changed)
    provider = providers[1]
    original = provider.generate
    seen = []

    async def fail_one(request):
        seen.append(request)
        if request.task_id == tasks[4]:
            raise ProviderUnavailableError('one video failed')
        return await original(request)

    provider.generate = fail_one
    # A new application/container reads only persisted state, not the old queue in memory.
    app = create_app(client.app.state.container.settings,
                     prompt_provider=providers[0], video_provider=provider)
    with TestClient(app) as restarted:
        restarted.portal.call(app.state.container.generation_queue._queue.join)
        assert [request.task_id for request in seen] == tasks
        assert [request.final_prompt for request in seen] == [f'Frozen {i}' for i in range(20)]
        for i, job in enumerate(jobs):
            stored = app.state.container.generation_service.get_job(job)
            assert stored.status == (JobStatus.FAILED if i == 4 else JobStatus.COMPLETED)
        provider.generate = original
        retry = _submit(restarted, project, tasks[4])
        restarted.portal.call(app.state.container.generation_queue._queue.join)
        assert retry != jobs[4]
        assert app.state.container.generation_service.get_job(jobs[4]).status == JobStatus.FAILED
        assert app.state.container.generation_service.get_job(retry).status == JobStatus.COMPLETED


@pytest.mark.parametrize('resumable', [False, True])
def test_scheduler_resumes_existing_remote_job_or_reports_interruption(
    client, providers, resumable,
):
    project = _project(client)['id']
    task = _task(client, project, '镜头', '原始内容')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    provider = providers[1]
    resume_calls = []
    if resumable:
        provider.capability = replace(provider.capability, job_resumption=True)

        async def resume(job_id):
            from shotmill.domain.providers import GeneratedOutput, VideoGenerationResponse
            resume_calls.append(job_id)
            return VideoGenerationResponse('existing-remote', (
                GeneratedOutput('resumed.mp4', b'existing-output', 'video/mp4'),
            ))

        provider.resume = resume
    job_id = _submit(client, project, task)
    started = utcnow()
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = started
        uow.jobs.update_runtime(job)
        current = uow.tasks.get(task)
        current.state = TaskState.RUNNING
        uow.tasks.update(current)
    before = service.get_job(job_id)
    app = create_app(client.app.state.container.settings,
                     prompt_provider=providers[0], video_provider=provider)
    with TestClient(app) as restarted:
        restarted.portal.call(app.state.container.generation_queue._queue.join)
        after = app.state.container.generation_service.get_job(job_id)
        assert after.status == (JobStatus.COMPLETED if resumable else JobStatus.FAILED)
        assert after.started_at == before.started_at
        assert after.final_prompt_snapshot == before.final_prompt_snapshot
        assert after.params_snapshot == before.params_snapshot
        if not resumable:
            assert after.error_code == 'GENERATION_INTERRUPTED'
        assert resume_calls == ([job_id] if resumable else [])
        assert not provider.requests  # never submit a second paid generation


@pytest.mark.parametrize('prompt_fails', [False, True])
def test_scheduler_queues_run_concurrently_without_prompt_clobbering_video_state(
    client, providers, prompt_fails,
):
    project = _project(client)['id']
    task = _task(client, project, '并行镜头', '原始内容')['id']
    container = client.app.state.container
    prompt_provider, video_provider = providers
    original_prompt, original_video = prompt_provider.enhance, video_provider.generate

    async def scenario():
        prompt_entered, video_entered = asyncio.Event(), asyncio.Event()
        release_prompt, release_video = asyncio.Event(), asyncio.Event()

        async def prompt(request):
            prompt_entered.set()
            await release_prompt.wait()
            if prompt_fails:
                raise ProviderUnavailableError('prompt failure must not stop video')
            return await original_prompt(request)

        async def video(request):
            video_entered.set()
            await release_video.wait()
            return await original_video(request)

        prompt_provider.enhance, video_provider.generate = prompt, video
        try:
            job = await container.generation_service.submit(project, task)
            await container.batch_production_service.create_prompt_batch(
                project, task_ids=[task], include_project_background=False,
                include_previous_task_summary=False,
            )
            await asyncio.wait_for(asyncio.gather(prompt_entered.wait(), video_entered.wait()), 2)
            release_prompt.set()
            await container.prompt_enhancement_queue._queue.join()
            with container.generation_service.uow_factory() as uow:
                assert uow.tasks.get(task).state == TaskState.RUNNING
                assert uow.jobs.get(job.id).status == JobStatus.RUNNING
            release_video.set()
            await container.generation_queue._queue.join()
            assert container.generation_service.get_job(job.id).status == JobStatus.COMPLETED
            assert video_provider.requests[0].final_prompt == '原始内容'
        finally:
            release_prompt.set()
            release_video.set()
            await container.prompt_enhancement_queue._queue.join()
            await container.generation_queue._queue.join()
            prompt_provider.enhance, video_provider.generate = original_prompt, original_video

    client.portal.call(scenario)
