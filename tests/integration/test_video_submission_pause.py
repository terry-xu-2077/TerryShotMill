from shotmill.application.container import build_container
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.errors import ProviderUnavailableError
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue


def test_offline_before_submission_keeps_snapshot_and_waits_for_user_retry(client, providers):
    project_id = _project(client)["id"]
    task_id = _task(client, project_id, "镜头", "原提示词")["id"]
    container = client.app.state.container
    service = container.generation_service
    queue = HeldQueue()
    service.attach_queue(queue)
    video = providers[1]
    original_generate = video.generate
    attempts = []
    available = False

    async def generate(request):
        attempts.append(request.job_id)
        if not available:
            raise ProviderUnavailableError("服务器无响应")
        return await original_generate(request)

    video.generate = generate
    response = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task_id}/generation", json={},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    assert queue.jobs == [job_id]
    original_job = service.get_job(job_id)

    client.portal.call(service.execute, job_id)
    with service.uow_factory() as uow:
        job = uow.jobs.get(job_id)
        assert job.status == JobStatus.QUEUED
        assert job.started_at is None
        assert job.error_code == "GENERATION_SERVICE_OFFLINE"
        assert job.error_message == "服务器未响应"
        assert job.final_prompt_snapshot == original_job.final_prompt_snapshot
        assert job.assets_snapshot == original_job.assets_snapshot
        assert job.context_snapshot == original_job.context_snapshot
        assert job.params_snapshot == original_job.params_snapshot
        assert uow.runtime_controls.get(job_id).paused
        assert uow.tasks.get(task_id).state == TaskState.QUEUED
    reopened = build_container(container.settings)
    try:
        reopened.project_documents.load_recent()
        assert reopened.generation_service.get_job(job_id).status == JobStatus.QUEUED
        with reopened.generation_service.uow_factory() as uow:
            assert uow.runtime_controls.get(job_id).paused
    finally:
        reopened.engine.dispose()
    workspace = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert workspace["tasks"][0]["generationStatusNote"] == "已挂起 · 服务器未响应"
    assert workspace["runtime"]["videoJobs"][0]["retrySubmission"] is True

    retry_url = f"/api/v1/projects/{project_id}/runtime/video/{job_id}"
    assert client.post(retry_url, json={"action": "resume"}).status_code == 200
    assert queue.jobs == [job_id, job_id]
    client.portal.call(service.execute, job_id)
    assert service.get_job(job_id).status == JobStatus.QUEUED
    assert attempts == [job_id, job_id]

    available = True
    assert client.post(retry_url, json={"action": "resume"}).status_code == 200
    client.portal.call(service.execute, job_id)
    finished = service.get_job(job_id)
    assert finished.status == JobStatus.COMPLETED
    assert finished.final_prompt_snapshot == original_job.final_prompt_snapshot
    assert finished.error_code is None
    assert attempts == [job_id, job_id, job_id]
    assert len(video.requests) == 1
    with service.uow_factory() as uow:
        assert len(uow.jobs.list_by_task(task_id)) == 1
        assert len(uow.results.list_by_task(task_id)) == 1
