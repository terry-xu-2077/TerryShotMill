from io import BytesIO

from shotmill.application.project_import_preflight import preflight_project_import
from shotmill.domain.entities import ContextLink, Scene, TaskAssetBinding, TaskPlacement, utcnow
from test_batch_review_api import _project, _task
from test_prompt_batch_recovery import HeldQueue
from test_two_instance_isolation import independent_server


def test_two_process_history_roundtrip_preserves_archives_and_missing_context(client, tmp_path):
    container = client.app.state.container
    project = _project(client)["id"]
    first = _task(client, project, "History source", "Original prompt")["id"]
    second = _task(client, project, "Context target", "Target prompt")["id"]
    asset = container.asset_service.import_bytes(project, "input.png", b"historical-input")
    with container.generation_service.uow_factory() as uow:
        task = uow.tasks.get(first)
        task.asset_bindings = [TaskAssetBinding(asset.id, "<Picture 1>")]
        uow.tasks.update(task)
    prompt_queue = HeldQueue()
    prompt = container.batch_production_service
    prompt.attach_queue(prompt_queue)
    enhanced = client.post(f"/api/v1/projects/{project}/prompt-enhancement-batches", json={
        "taskIds": [first],
    })
    assert enhanced.status_code == 202
    assert client.portal.call(prompt._execute_prompt_job, prompt_queue.jobs[0]).state == "completed"
    generation = container.generation_service
    generation.attach_queue(HeldQueue())
    for _ in range(2):
        response = client.post(f"/api/v1/projects/{project}/tasks/{first}/generation", json={})
        assert response.status_code == 202, response.text
        client.portal.call(generation.execute, response.json()["id"])
    with generation.uow_factory() as uow:
        task = uow.tasks.get(first)
        task.archived_at = utcnow()
        uow.tasks.update(task)
        target = uow.tasks.get(second)
        target.deleted_at = utcnow()
        uow.tasks.update(target)
        uow.story_structure.add_scene(Scene("hidden", project, 2, "Hidden scene", "", 2))
        uow.story_structure.place_task(project, TaskPlacement(first, "hidden", 7))
        uow.contexts.replace_for_target(second, [
            ContextLink("live", project, first, second, "last-frame",
                        source_result_id=task.primary_result_id),
            ContextLink("gone", project, "deleted-source", second, "semantic",
                        source_deleted_at=utcnow(), source_task_title="Deleted source"),
        ])
    response = client.get(f"/api/v1/projects/{project}/export")
    assert response.status_code == 200, response.text
    payload = response.content
    project_ids = {project}
    with independent_server(tmp_path / "left") as (left, _), independent_server(
        tmp_path / "right",
    ) as (right, _):
        for peer in (left, right, left):
            imported = peer.post("/api/v1/projects/import", files={
                "file": ("history.zip", payload, "application/zip"),
            })
            assert imported.status_code == 201, imported.text
            imported_id = imported.json()["projectId"]
            assert imported_id not in project_ids
            project_ids.add(imported_id)
            exported = peer.get(f"/api/v1/projects/{imported_id}/export")
            assert exported.status_code == 200, exported.text
            payload = exported.content
            with preflight_project_import(BytesIO(payload)) as package:
                source = package.source
                tasks = {task.title: task for task in source.tasks}
                history, target = tasks["History source"], tasks["Context target"]
                assert history.archived_at is not None and target.deleted_at is not None
                assert len(source.jobs) == len(source.results) == 2
                assert len(source.prompt_jobs) == len(source.prompt_revisions) == 1
                assert source.prompt_jobs[0].revision_id == source.prompt_revisions[0].id
                assert history.primary_result_id in {result.id for result in source.results}
                links = {link.kind: link for link in source.contexts}
                assert links["last-frame"].source_task_id == history.id
                assert links["last-frame"].source_result_id == history.primary_result_id
                assert links["semantic"].source_deleted_at is not None
                assert links["semantic"].source_task_id not in {task.id for task in source.tasks}
                scene = next(scene for scene in source.scenes if scene.title == "Hidden scene")
                assert any(p.task_id == history.id and p.scene_id == scene.id and p.order_key == 7
                           for p in source.placements)
                for job in source.jobs:
                    relative = job.assets_snapshot[0]["projectRelativePath"]
                    assert package.files[relative].read_bytes() == b"historical-input"
                relative = source.prompt_jobs[0].source_snapshot["media"][0]["projectRelativePath"]
                assert package.files[relative].read_bytes() == b"historical-input"
