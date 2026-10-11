import asyncio
import hashlib
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from shotmill.app import create_app
from shotmill.application.generation_service import GenerationQueue
from shotmill.domain.entities import utcnow
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.errors import ProviderUnavailableError
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def _submit(client, project, task):
    response = client.post(f'/api/v1/projects/{project}/tasks/{task}/generation', json={})
    assert response.status_code == 202, response.text
    return response.json()['id']


@pytest.mark.parametrize('digest', ['correct', 'missing', 'wrong'])
def test_negotiated_profile_persists_and_recovery_ignores_new_endpoint(
    client, monkeypatch, bridge_health, bridge_snapshot, digest,
):
    project = _project(client)['id']
    task = _task(client, project, '协议冻结', '提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    calls = []
    recovering = False

    def handler(request):
        calls.append((request.method, request.url.host, request.url.path))
        assert request.url.host == 'desktop'
        assert request.url.path.startswith('/terryflow/v1/')
        if recovering:
            assert request.method == 'GET'
            if '/files/' in request.url.path:
                headers = {} if digest == 'missing' else {
                    'x-content-sha256': hashlib.sha256(b'video').hexdigest()
                    if digest == 'correct' else '0' * 64,
                }
                return httpx.Response(200, content=b'video', headers=headers)
            assert '/jobs/' in request.url.path
            return httpx.Response(200, json={
                'status': 'completed', 'promptId': 'original',
                'results': [{'filename': 'clip.mp4'}],
            })
        if request.url.path.endswith('/health'):
            return httpx.Response(200, json=bridge_health)
        if request.url.path.endswith('/snapshot'):
            return httpx.Response(200, json={'snapshot': bridge_snapshot()})
        if request.url.path.endswith('/workflows'):
            return httpx.Response(200, json={'workflows': [{'id': 'w.json', 'inputs': []}]})
        assert request.url.path.endswith('/validate')
        return httpx.Response(200, json={'ok': True})

    monkeypatch.setattr(service, 'provider', ComfyUIVideoGenerationProvider(
        'http://desktop', Path('w.json'), transport=httpx.MockTransport(handler),
    ))
    job_id = _submit(client, project, task)
    frozen = service.get_job(job_id).provider_profile_snapshot
    assert frozen['bridgeAgreement']['apiPrefix'] == '/terryflow/v1'
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        uow.jobs.update_runtime(job)
    recovering = True
    calls.clear()
    monkeypatch.setattr(service, 'provider', ComfyUIVideoGenerationProvider(
        'http://new-desktop', Path('different.json'), transport=httpx.MockTransport(handler),
    ))

    async def recover():
        await service.execute(job_id, recover=True)

    client.portal.call(recover)
    stored = service.get_job(job_id)
    assert stored.status == (JobStatus.COMPLETED if digest == 'correct' else JobStatus.FAILED)
    if digest != 'correct':
        assert stored.error_code.startswith('COMFYUI_DOWNLOAD_CHECKSUM_')
    assert stored.provider_profile_snapshot == frozen
    assert calls == [
        ('GET', 'desktop', f'/terryflow/v1/jobs/{job_id}'),
        ('GET', 'desktop', f'/terryflow/v1/results/{job_id}/files/0'),
    ]
    with service.uow_factory() as uow:
        assert uow.results.count_by_task(task) == (1 if digest == 'correct' else 0)


def test_lost_submission_receipt_survives_restart_without_new_generation(client, monkeypatch):
    project = _project(client)['id']
    task = _task(client, project, '提交回执丢失', '冻结提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    calls = []

    async def scenario():
        observed_unknown = asyncio.Event()
        recovered = False

        async def handler(request):
            calls.append((request.method, request.url.path))
            if request.method == 'POST':
                assert service.get_job(job_id).runtime_progress['submissionState'] == 'sending'
                raise httpx.ReadTimeout('server accepted; response lost', request=request)
            if not recovered:
                observed_unknown.set()
                return httpx.Response(404)
            if '/files/' in request.url.path:
                return httpx.Response(200, content=b'original-result')
            return httpx.Response(200, json={
                'status': 'completed', 'promptId': 'original-remote',
                'results': [{'filename': 'clip.mp4'}],
            })

        async def validate(*args, **kwargs):
            return []

        async def upload(*args, **kwargs):
            return {}

        def provider():
            item = ComfyUIVideoGenerationProvider(
                'http://desktop', None, transport=httpx.MockTransport(handler),
                poll_interval_seconds=0.001,
            )
            item.frozen_workflow_id = 'workflow.json'
            item.workflow_snapshot = {'prompt': {}}
            item._validate_workflow_inputs = validate
            item._upload_assets = upload
            return item

        monkeypatch.setattr(service, '_execution_provider', lambda _: provider())
        work = asyncio.create_task(service.execute(job_id))
        try:
            await asyncio.wait_for(observed_unknown.wait(), 3)
        finally:
            work.cancel()
            with pytest.raises(asyncio.CancelledError):
                await work
        stored = service.get_job(job_id)
        assert stored.status == JobStatus.RUNNING
        assert stored.runtime_progress['submissionState'] == 'uncertain'
        assert stored.completed_at is None
        recovered = True
        await service.execute(job_id, recover=True)
        stored = service.get_job(job_id)
        assert stored.status == JobStatus.COMPLETED
        assert stored.provider_job_id == 'original-remote'
        assert stored.runtime_progress['submissionState'] == 'accepted'
        with service.uow_factory() as uow:
            assert uow.results.count_by_task(task) == 1
        assert [method for method, _ in calls].count('POST') == 1

    client.portal.call(scenario)


@pytest.mark.parametrize('stop_requested', [False, True])
def test_recovery_of_durable_cancel_receipt_never_creates_result(
    client, monkeypatch, stop_requested,
):
    project = _project(client)['id']
    task = _task(client, project, '取消恢复', '提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        job.runtime_progress = {'submissionState': 'uncertain', 'stopRequested': stop_requested}
        uow.jobs.update_runtime(job)
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={'status': 'cancelled', 'jobId': job_id})

    provider = ComfyUIVideoGenerationProvider(
        'http://desktop', None, transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(service, '_execution_provider', lambda _: provider)
    async def recover():
        await service.execute(job_id, recover=True)

    client.portal.call(recover)
    stored = service.get_job(job_id)
    assert stored.status == JobStatus.CANCELLED
    assert stored.error_code == 'USER_STOPPED'
    assert stored.completed_at is not None
    with service.uow_factory() as uow:
        assert uow.results.count_by_task(task) == 0
        assert uow.tasks.get(task).state == TaskState.READY
    expected = [('GET', f'/shotmill/v1/jobs/{job_id}')]
    if stop_requested:
        expected.insert(0, ('POST', f'/shotmill/v1/jobs/{job_id}/cancel-submission'))
    assert calls == expected


def test_exit_before_stop_receipt_recovers_original_stop_intent(client, monkeypatch):
    project = _project(client)['id']
    task = _task(client, project, '停止中退出', '提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        job.runtime_progress = {'submissionState': 'uncertain'}
        uow.jobs.update_runtime(job)
    calls = []

    async def scenario():
        entered = asyncio.Event()
        restarted = False

        async def handler(request):
            calls.append((request.method, request.url.path))
            if not restarted:
                entered.set()
                await asyncio.Event().wait()
            return httpx.Response(200, json={'status': 'cancelled', 'jobId': job_id})

        def provider(_):
            return ComfyUIVideoGenerationProvider(
                'http://desktop', None, transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(service, '_execution_provider', provider)
        stopping = asyncio.create_task(service.stop_job(project, job_id))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
        finally:
            stopping.cancel()
            with pytest.raises(asyncio.CancelledError):
                await stopping
        stored = service.get_job(job_id)
        assert stored.runtime_progress['stopRequested'] is True
        assert stored.status == JobStatus.RUNNING
        restarted = True
        await service.execute(job_id, recover=True)
        assert service.get_job(job_id).status == JobStatus.CANCELLED
        with service.uow_factory() as uow:
            assert uow.results.count_by_task(task) == 0

    client.portal.call(scenario)
    assert calls == [
        ('POST', f'/shotmill/v1/jobs/{job_id}/cancel-submission'),
        ('POST', f'/shotmill/v1/jobs/{job_id}/cancel-submission'),
        ('GET', f'/shotmill/v1/jobs/{job_id}'),
    ]


def test_lan_disconnection_keeps_job_running_and_collects_once(client, monkeypatch):
    project = _project(client)['id']
    task = _task(client, project, '局域网任务', '冻结提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        uow.jobs.update_runtime(job)

    async def scenario():
        offline, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def handler(request):
            calls.append((request.method, request.url.path))
            assert request.method == 'GET'
            if len(calls) == 1:
                raise httpx.ConnectError('laptop offline', request=request)
            await release.wait()
            if '/files/' in request.url.path:
                return httpx.Response(
                    200, content=b'original-video', headers={'content-type': 'video/mp4'}
                )
            return httpx.Response(200, json={
                'status': 'completed', 'promptId': 'original-remote',
                'results': [{'filename': 'original.mp4'}],
            })

        provider = ComfyUIVideoGenerationProvider('http://desktop', None,
            transport=httpx.MockTransport(handler), poll_interval_seconds=0.1)

        def set_progress(callback):
            async def report(update):
                await callback(update)
                if update.get('connectionState') == 'reconnecting':
                    offline.set()
            provider.progress_callback = report

        provider.set_progress_callback = set_progress
        monkeypatch.setattr(service, '_execution_provider', lambda _: provider)
        work = asyncio.create_task(service.execute(job_id, recover=True))
        try:
            await asyncio.wait_for(offline.wait(), 3)
            stored = service.get_job(job_id)
            assert stored.status == JobStatus.RUNNING
            assert stored.completed_at is None
            assert stored.runtime_progress['connectionState'] == 'reconnecting'
            await service.execute(job_id, recover=True)
        finally:
            release.set()
            await asyncio.wait_for(work, 3)
        stored = service.get_job(job_id)
        assert stored.status == JobStatus.COMPLETED
        assert stored.provider_job_id == 'original-remote'
        assert stored.runtime_progress['collectionState'] == 'saved'
        await service.execute(job_id, recover=True)
        with service.uow_factory() as uow:
            assert uow.results.count_by_task(task) == 1
        assert all(method == 'GET' for method, _ in calls)

    client.portal.call(scenario)


def test_queue_shutdown_detaches_local_wait_without_cancelling_remote_job(client, providers):
    project = _project(client)['id']
    task = _task(client, project, '关闭应用', '保留原任务')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    provider = providers[1]
    original = provider.generate
    provider.capability = replace(provider.capability, job_resumption=True)
    stopped = []
    submitted, resumed = [], []

    async def scenario():
        entered, detached = asyncio.Event(), asyncio.Event()

        async def generate(_request):
            submitted.append(_request.job_id)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                detached.set()

        async def stop(_job):
            stopped.append(_job)

        provider.generate = generate
        provider.stop = stop
        queue = GenerationQueue(service)
        try:
            await queue.start()
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(queue.stop(), 3)
            assert detached.is_set()
            assert service.get_job(job_id).status == JobStatus.RUNNING
            assert not stopped
            with service.uow_factory() as uow:
                assert uow.results.count_by_task(task) == 0

            async def resume(original_job_id):
                from shotmill.domain.providers import GeneratedOutput, VideoGenerationResponse
                resumed.append(original_job_id)
                return VideoGenerationResponse('original-remote', (
                    GeneratedOutput('original.mp4', b'original-output', 'video/mp4'),
                ))

            provider.resume = resume
            await queue.start()
            await asyncio.wait_for(queue._queue.join(), 3)
            await queue.stop()
            assert service.get_job(job_id).status == JobStatus.COMPLETED
            assert submitted == [job_id]
            assert resumed == [job_id]
            assert not stopped
            with service.uow_factory() as uow:
                assert uow.results.count_by_task(task) == 1
        finally:
            for worker in queue._tasks:
                worker.cancel()
            await asyncio.gather(*queue._tasks, return_exceptions=True)
            provider.generate = original

    client.portal.call(scenario)


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
            raise RuntimeError('one video failed')
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
        if resumable:
            with app.state.container.generation_service.uow_factory() as uow:
                results = uow.results.list_by_task(task)
                assert len(results) == 1
                result_url = results[0].video_url
            saved_path = app.state.container.storage.resolve_read(
                project, result_url.removeprefix(f'/media/{project}/'),
            )
            assert saved_path.is_relative_to(app.state.container.project_documents.media_root(project))
            assert saved_path.read_bytes() == b'existing-output'
            assert restarted.get(result_url).content == b'existing-output'
    if resumable:
        def unexpected_resume(_job_id):
            raise AssertionError('saved result must not query the server again')

        provider.resume = unexpected_resume
        reopened_app = create_app(client.app.state.container.settings,
                                  prompt_provider=providers[0], video_provider=provider)
        with TestClient(reopened_app) as reopened:
            assert reopened_app.state.container.generation_service.get_job(job_id).status == JobStatus.COMPLETED
            assert reopened.get(result_url).content == b'existing-output'
            assert reopened.get(f'/api/v1/projects/{project}/workspace').json()['tasks'][0][
                'resultCount'
            ] == 1
        assert resume_calls == [job_id]


def test_confirmed_server_exit_fails_original_job_and_requires_manual_rerun(
    client, monkeypatch,
):
    project = _project(client)['id']
    task = _task(client, project, '中断镜头', '保留提示词')['id']
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    job_id = _submit(client, project, task)
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        job.runtime_progress = {'submissionState': 'accepted'}
        uow.jobs.update_runtime(job)
        current = uow.tasks.get(task)
        current.state = TaskState.RUNNING
        uow.tasks.update(current)
    original_prompt = service.get_job(job_id).final_prompt_snapshot
    original_execution_provider = service._execution_provider
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={
            'status': 'failed', 'promptId': 'original-remote',
            'error': {'code': 'server_exited', 'reason': 'unknown'},
        })

    provider = ComfyUIVideoGenerationProvider(
        'http://desktop', None, transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(service, '_execution_provider', lambda _: provider)

    async def recover():
        await service.execute(job_id, recover=True)

    client.portal.call(recover)
    failed = service.get_job(job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == 'GENERATION_SERVER_EXITED'
    assert '退出原因未知' in failed.error_message
    assert failed.final_prompt_snapshot == original_prompt
    assert calls == [('GET', f'/shotmill/v1/jobs/{job_id}')]
    workspace = client.get(f'/api/v1/projects/{project}/workspace').json()
    assert workspace['tasks'][0]['generationStatusNote'] == '服务器退出 · 原因未知'
    with service.uow_factory() as uow:
        assert uow.tasks.get(task).state == TaskState.FAILED
        assert uow.results.count_by_task(task) == 0
    monkeypatch.setattr(service, '_execution_provider', original_execution_provider)
    rerun = _submit(client, project, task)
    assert rerun != job_id
    assert service.get_job(job_id).status == JobStatus.FAILED


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
