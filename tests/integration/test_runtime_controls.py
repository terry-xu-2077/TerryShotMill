from copy import deepcopy

import pytest
from shotmill.application.batch_service import PromptEnhancementQueue
from shotmill.application.generation_service import GenerationQueue
from shotmill.domain.enums import JobStatus
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue
from test_video_queue_cancel import _submit


def setup_jobs(client, kind):
    project = _project(client)["id"]
    tasks = [_task(client, project, f"task{i}", f"content{i}")["id"] for i in range(3)]
    container = client.app.state.container
    service = (
        container.generation_service if kind == "video" else container.batch_production_service
    )
    held = HeldQueue()
    service.attach_queue(held)
    if kind == "video":
        jobs = [_submit(client, project, task) for task in tasks]
    else:
        response = client.post(
            f"/api/v1/projects/{project}/prompt-enhancement-batches", json={"taskIds": tasks}
        )
        assert response.status_code == 202, response.text
        jobs = held.jobs[:]
    return project, tasks, jobs, service


def action(client, project, kind, job, command):
    return client.post(f"/api/v1/projects/{project}/runtime/{kind}/{job}", json={"action": command})


@pytest.mark.parametrize("kind", ["video", "prompt"])
def test_persisted_pause_order_resume_remove_and_snapshot_integrity(client, kind, providers):
    project, tasks, jobs, service = setup_jobs(client, kind)
    with service.uow_factory() as uow:
        repo = uow.jobs if kind == "video" else uow.prompt_jobs
        before = deepcopy(repo.get(jobs[0]))
    assert action(client, project, kind, jobs[0], "pause").status_code == 200
    assert action(client, project, kind, jobs[2], "up").status_code == 200
    assert action(client, project, kind, jobs[2], "up").status_code == 200
    with service.uow_factory() as uow:
        repo = uow.jobs if kind == "video" else uow.prompt_jobs
        assert repo.get(jobs[0]) == before
        assert uow.runtime_controls.get(jobs[0]).paused
    executed = []
    method = "execute" if kind == "video" else "_execute_prompt_job"
    original = getattr(service, method)

    async def tracked(job_id, **kwargs):
        with service.uow_factory() as uow:
            if not uow.runtime_controls.get(job_id).paused:
                executed.append(job_id)
        return await original(job_id, **kwargs)

    setattr(service, method, tracked)
    # Fresh scheduler reconstructs persisted priority and suspension after restart.
    queue = GenerationQueue(service) if kind == "video" else PromptEnhancementQueue(service)
    service.attach_queue(queue)
    client.portal.call(queue.start)
    client.portal.call(queue._queue.join)
    assert executed == [jobs[2], jobs[1]]
    with service.uow_factory() as uow:
        repo = uow.jobs if kind == "video" else uow.prompt_jobs
        assert repo.get(jobs[0]).status == JobStatus.QUEUED
    assert action(client, project, kind, jobs[0], "resume").status_code == 200
    client.portal.call(queue._queue.join)
    assert executed == [jobs[2], jobs[1], jobs[0]]
    assert action(client, project, kind, jobs[0], "remove").status_code == 200
    with service.uow_factory() as uow:
        repo = uow.jobs if kind == "video" else uow.prompt_jobs
        assert repo.get(jobs[0]).status == JobStatus.COMPLETED
        assert uow.runtime_controls.get(jobs[0]).hidden
        if kind == "video":
            assert uow.results.list_by_task(tasks[0])
        else:
            assert uow.prompt_revisions.list_by_task(tasks[0])
    data = client.get("/api/v1/projects/runtime").json()
    runtime = next(p["runtime"] for p in data if p["project"]["id"] == project)
    items = (
        runtime["videoJobs"]
        if kind == "video"
        else [i for b in runtime["promptBatches"] for i in b["items"]]
    )
    assert jobs[0] not in [item["id"] for item in items]
    client.portal.call(queue.stop)


@pytest.mark.parametrize("kind", ["video", "prompt"])
def test_remove_queued_cancel_and_reject_running_or_foreign_jobs(client, kind):
    project, _, jobs, service = setup_jobs(client, kind)
    other = _project(client)["id"]
    assert action(client, other, kind, jobs[0], "remove").status_code == 404
    assert action(client, project, kind, jobs[0], "pause").status_code == 200
    assert action(client, project, kind, jobs[0], "remove").status_code == 200
    with service.uow_factory() as uow:
        repo = uow.jobs if kind == "video" else uow.prompt_jobs
        assert repo.get(jobs[0]).status == JobStatus.CANCELLED
        job = repo.get(jobs[1])
        job.status = JobStatus.RUNNING
        (repo.update_runtime if kind == "video" else repo.update)(job)
    for command in ["pause", "resume", "up", "down", "remove"]:
        assert action(client, project, kind, jobs[1], command).status_code == 409
    with service.uow_factory() as uow:
        assert not uow.runtime_controls.get(jobs[1]).hidden
        assert not uow.runtime_controls.get(jobs[1]).paused
