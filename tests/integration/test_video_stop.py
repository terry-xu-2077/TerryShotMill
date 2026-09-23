import asyncio

from shotmill.domain.enums import JobStatus
from shotmill.errors import ShotMillError
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue
from test_video_queue_cancel import _submit


def test_user_stop_is_persisted_distinct_from_failure_and_preserves_results(client, providers):
    project = _project(client)["id"]
    task = _task(client, project, "停止测试", "内容")["id"]
    service = client.app.state.container.generation_service
    service.attach_queue(HeldQueue())
    original = _submit(client, project, task)
    client.portal.call(service.execute, original)
    with service.uow_factory() as uow:
        primary = uow.tasks.get(task).primary_result_id
    job_id = _submit(client, project, task)
    provider = providers[1]

    async def scenario():
        entered, stopped = asyncio.Event(), asyncio.Event()

        async def generate(request):
            entered.set()
            await stopped.wait()
            raise ShotMillError("SHOTMILL_BRIDGE_JOB_FAILED", "execution_interrupted", 502)

        async def stop(requested):
            assert requested == job_id
            assert service.get_job(job_id).runtime_progress["stopRequested"]
            stopped.set()

        provider.generate, provider.stop = generate, stop
        runner = asyncio.create_task(service.execute(job_id))
        await entered.wait()
        await service.stop_job(project, job_id)
        await runner

    client.portal.call(scenario)
    job = service.get_job(job_id)
    assert job.status == JobStatus.CANCELLED
    assert job.error_code == "USER_STOPPED"
    assert job.error_message == "用户停止"
    client.portal.call(service.stop_job, project, job_id)
    with service.uow_factory() as uow:
        assert uow.tasks.get(task).primary_result_id == primary
        assert uow.results.count_by_task(task) == 1
    workspace = client.get(f"/api/v1/projects/{project}/workspace").json()
    assert workspace["tasks"][0]["generationStatusNote"] == "用户停止"
    item = next(j for j in workspace["runtime"]["videoJobs"] if j["id"] == job_id)
    assert item["statusNote"] == "用户停止"
    assert item["error"] is None
    assert client.post(f"/api/v1/projects/foreign/jobs/{job_id}/stop").status_code == 404
