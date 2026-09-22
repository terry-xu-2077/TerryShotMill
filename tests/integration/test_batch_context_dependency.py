from pathlib import Path

from shotmill.domain.providers import GeneratedOutput, VideoGenerationResponse


class HeldQueue:
    def __init__(self):
        self.ids = []

    async def enqueue(self, job_id):
        self.ids.append(job_id)


def prepare(client, providers):
    service = client.app.state.container.generation_service
    queue = HeldQueue()
    service.attach_queue(queue)

    async def generate(request):
        providers[1].requests.append(request)
        return VideoGenerationResponse(
            "fixture",
            (
                GeneratedOutput(
                    "clip.mp4",
                    Path("backend/shotmill/devtools/fixtures/preview.mp4").read_bytes(),
                    "video/mp4",
                ),
            ),
        )

    providers[1].generate = generate
    project = client.post("/api/v1/projects", json={"title": "Sequential context"}).json()["id"]
    route = f"/api/v1/projects/{project}"
    tasks = [
        client.post(route + "/tasks", json={"title": name, "userPrompt": name}).json()["id"]
        for name in ("First", "Second")
    ]
    return service, queue, route, tasks


def test_batch_binds_new_upstream_result_at_execution_and_keeps_input_frozen(client, providers):
    service, queue, route, tasks = prepare(client, providers)
    response = client.post(route + "/video-generation-batches", json={"taskIds": tasks})
    assert response.status_code == 202, response.text
    assert response.json()["warnings"] == []
    first, second = queue.ids
    snapshot = service.get_job(second)
    assert snapshot.context_snapshot["dependency"]["sourceJobId"] == first
    # Even if reordered ahead of its source, no provider call is allowed.
    client.portal.call(service.execute, second)
    assert providers[1].requests == []
    assert service.get_job(second).status.value == "queued"
    with service.uow_factory() as uow:
        target = uow.tasks.get(tasks[1])
        target.final_prompt = "Changed after enqueue"
        uow.tasks.update(target)
    client.portal.call(service.execute, first)
    client.portal.call(service.execute, second)
    completed = service.get_job(second)
    assert completed.status.value == "completed"
    assert completed.context_snapshot == snapshot.context_snapshot
    assert completed.final_prompt_snapshot == snapshot.final_prompt_snapshot
    assert providers[1].requests[-1].final_prompt == "Second"
    assert providers[1].requests[-1].params["contextMode"] == "尾帧承接"
    assert providers[1].requests[-1].assets[-1].media_type == "image"
    with service.uow_factory() as uow:
        result = uow.results.get(completed.execution_context["media"][0]["sourceResultId"])
    assert result.job_id == first


def test_dependency_failure_requires_explicit_continue_and_never_uses_old_result(client, providers):
    from shotmill.domain.enums import JobStatus

    service, queue, route, tasks = prepare(client, providers)
    # An old success exists, but the new batch must bind its own source Job.
    old = client.post(route + f"/tasks/{tasks[0]}/generation", json={}).json()["id"]
    client.portal.call(service.execute, old)
    queue.ids.clear()
    response = client.post(route + "/video-generation-batches", json={"taskIds": tasks})
    assert response.status_code == 202
    first, second = queue.ids
    with service.uow_factory() as uow:
        source = uow.jobs.get(first)
        source.status = JobStatus.FAILED
        uow.jobs.update_runtime(source)
    client.portal.call(service.execute, second)
    assert len(providers[1].requests) == 1
    pending = service.get_job(second)
    assert pending.status == JobStatus.QUEUED
    assert pending.execution_context is None
    with service.uow_factory() as uow:
        assert uow.runtime_controls.get(second).paused
    workspace = client.get(route + "/workspace").json()
    target = next(task for task in workspace["tasks"] if task["id"] == tasks[1])
    assert target["generationWarnings"]
    runtime = next(item for item in workspace["runtime"]["videoJobs"] if item["id"] == second)
    assert runtime["continuationFallback"]
    response = client.post(route + f"/runtime/video/{second}", json={"action": "resume"})
    assert response.status_code == 200
    client.portal.call(service.execute, second)
    assert service.get_job(second).status == JobStatus.COMPLETED
    assert providers[1].requests[-1].params["contextMode"] == "不承接"
    assert not providers[1].requests[-1].assets
    # Binding is write-once even after completion.
    with service.uow_factory() as uow:
        bound = uow.jobs.bind_execution_context(second, {"mode": "tampered"})
    assert bound["mode"] == "不承接"


def test_restart_ordering_and_suspended_source_do_not_block_independent_work(client, providers):
    from shotmill.application.generation_service import GenerationQueue

    service, held, route, tasks = prepare(client, providers)
    independent = client.post(
        route + "/tasks",
        json={
            "title": "Independent",
            "userPrompt": "Independent",
            "generation": {"contextMode": "不承接"},
        },
    ).json()["id"]
    response = client.post(
        route + "/video-generation-batches", json={"taskIds": tasks + [independent]}
    )
    assert response.status_code == 202
    first, second, third = held.ids
    assert (
        client.post(route + f"/runtime/video/{first}", json={"action": "pause"}).status_code == 200
    )
    assert client.post(route + f"/runtime/video/{second}", json={"action": "up"}).status_code == 200
    queue = GenerationQueue(service, workers=2)
    service.attach_queue(queue)
    client.portal.call(queue.start)
    client.portal.call(queue._queue.join)
    assert [request.task_id for request in providers[1].requests] == [independent]
    workspace = client.get(route + "/workspace").json()
    summary = next(task for task in workspace["tasks"] if task["id"] == tasks[1])
    assert summary["generationStatusNote"] == "等待上一任务结果"
    assert summary["generationWarnings"] == []
    assert (
        client.post(route + f"/runtime/video/{first}", json={"action": "resume"}).status_code == 200
    )
    client.portal.call(queue._queue.join)
    assert [request.task_id for request in providers[1].requests] == [independent, *tasks]
    assert service.get_job(second).execution_context["sourceJobId"] == first
    client.portal.call(queue.stop)


def test_removal_wakes_dependent_but_does_not_generate_without_consent(client, providers):
    service, queue, route, tasks = prepare(client, providers)
    client.post(route + "/video-generation-batches", json={"taskIds": tasks})
    first, second = queue.ids
    client.portal.call(service.execute, second)
    queue.ids.clear()
    assert (
        client.post(route + f"/runtime/video/{first}", json={"action": "remove"}).status_code == 200
    )
    assert second in queue.ids
    client.portal.call(service.execute, second)
    assert service.get_job(second).error_code == "CONTEXT_DEPENDENCY_UNAVAILABLE"
    assert providers[1].requests == []


def test_partial_selection_keeps_missing_context_warning(client, providers):
    service, queue, route, tasks = prepare(client, providers)
    response = client.post(route + "/video-generation-batches", json={"taskIds": [tasks[1]]})
    assert response.status_code == 202
    assert response.json()["warnings"]
    job = service.get_job(queue.ids[0])
    assert "dependency" not in job.context_snapshot
    assert job.params_snapshot["contextMode"] == "不承接"


def test_three_task_chain_uses_each_immediate_predecessor(client, providers):
    service, queue, route, tasks = prepare(client, providers)
    third = client.post(route + "/tasks", json={"title": "Third", "userPrompt": "Third"}).json()[
        "id"
    ]
    response = client.post(
        route + "/video-generation-batches", json={"taskIds": [third, *reversed(tasks)]}
    )
    assert response.status_code == 202
    first_job, second_job, third_job = queue.ids
    for job_id in (first_job, second_job, third_job):
        client.portal.call(service.execute, job_id)
    assert service.get_job(second_job).execution_context["sourceJobId"] == first_job
    assert service.get_job(third_job).execution_context["sourceJobId"] == second_job
    assert [request.task_id for request in providers[1].requests] == [*tasks, third]


def test_unreadable_upstream_video_is_disclosed_before_downstream_generation(client, providers):
    service, queue, route, tasks = prepare(client, providers)
    client.post(route + "/video-generation-batches", json={"taskIds": tasks})
    first, second = queue.ids
    client.portal.call(service.execute, first)
    with service.uow_factory() as uow:
        result = uow.results.list_by_task(tasks[0])[0]
    path = result.video_url.split(f"/media/{result.project_id}/", 1)[1]
    service.storage.resolve(result.project_id, path).write_bytes(b"invalid video")
    client.portal.call(service.execute, second)
    assert len(providers[1].requests) == 1
    assert service.get_job(second).error_code == "CONTEXT_DEPENDENCY_UNAVAILABLE"
    assert service.get_job(second).execution_context is None
    with service.uow_factory() as uow:
        assert uow.runtime_controls.get(second).paused


def test_batch_context_ignores_later_primary_result_changes(client, providers):
    service, queue, route, tasks = prepare(client, providers)
    client.post(route + "/video-generation-batches", json={"taskIds": tasks})
    first, second = queue.ids
    client.portal.call(service.execute, first)
    newer = client.post(route + f"/tasks/{tasks[0]}/generation", json={}).json()["id"]
    client.portal.call(service.execute, newer)
    client.portal.call(service.execute, second)
    with service.uow_factory() as uow:
        primary = uow.results.get(uow.tasks.get(tasks[0]).primary_result_id)
        used = uow.results.get(
            service.get_job(second).execution_context["media"][0]["sourceResultId"]
        )
    assert primary.job_id == newer
    assert used.job_id == first
