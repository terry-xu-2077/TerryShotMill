from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from shotmill.application import (
    asset_service,
    project_service,
    prompt_enhancement_service,
    prompt_review,
    result_service,
    task_service,
)
from shotmill.application.asset_service import AssetService
from shotmill.application.project_service import ProjectService
from shotmill.application.prompt_enhancement_service import PromptEnhancementService
from shotmill.application.prompt_review import PromptReviewService
from shotmill.application.result_service import ResultService
from shotmill.application.task_service import SaveTaskData, TaskService
from shotmill.domain.entities import AiPromptRevision, Job, Result
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError
from shotmill.media.storage import MediaStorage
from test_lifecycle_service import lifecycle  # noqa: F401


@pytest.mark.parametrize("first", ["edit", "lifecycle"])
@pytest.mark.parametrize("action", ["archive", "trash"])
@pytest.mark.parametrize("writer,target", [
    ("project", "project"), ("task", "project"), ("task", "task"),
    ("create", "project"), ("reorder", "project"),
    ("preference", "project"), ("preference", "task"),
    ("asset-edit", "project"), ("asset-delete", "project"), ("asset-upload", "project"),
    ("primary", "project"), ("primary", "task"),
    ("review", "project"), ("review", "task"),
    ("revision", "project"), ("revision", "task"),
])
def test_edit_and_lifecycle_are_serialized(
    lifecycle, tmp_path, monkeypatch, first, action, writer, target,  # noqa: F811
):
    lifecycle_service, factory = lifecycle
    storage = MediaStorage(tmp_path / "media")
    assets = AssetService(factory, storage)
    asset = assets.import_bytes("p", "original.txt", b"original")
    with factory() as uow:
        task = uow.tasks.get("t0")
        task.user_prompt = task.final_prompt = "Original prompt"
        uow.tasks.update(task)
        uow.jobs.add(Job(
            id="job", project_id="p", task_id="t0", status=JobStatus.COMPLETED,
            final_prompt_snapshot="Original prompt", task_content_snapshot={}, assets_snapshot=[],
            generation_profile_snapshot={}, provider_profile_snapshot={}, params_snapshot={},
            context_snapshot={},
        ))
        uow.results.add(Result(
            id="result", project_id="p", task_id="t0", job_id="job", video_url="/media/clip.mp4",
        ))
        uow.prompt_revisions.add(AiPromptRevision(
            id="revision", project_id="p", task_id="t0", source_user_prompt="Original prompt",
            output_prompt="Selected prompt", asset_ids=[], project_background_used=False,
            previous_task_summary_used=False, target_skill="minimax-h3", skill_version="1",
        ))
    module = {
        "project": project_service, "primary": result_service, "review": prompt_review,
        "revision": prompt_enhancement_service, "asset-edit": asset_service,
        "asset-delete": asset_service, "asset-upload": asset_service,
    }.get(writer, task_service)
    entered, release = Event(), Event()
    if first == "edit":
        original = module.require_writable
        checked = 0

        def hold(*args):
            nonlocal checked
            original(*args)
            checked += 1
            if writer == "asset-upload" and checked == 1:
                return  # Upload's preflight is outside its final commit transaction.
            entered.set()
            assert release.wait(5)

        monkeypatch.setattr(module, "require_writable", hold)
    else:
        original = lifecycle_service._ensure_idle

        def hold(*args):
            original(*args)
            entered.set()
            assert release.wait(5)

        monkeypatch.setattr(lifecycle_service, "_ensure_idle", hold)

    def edit():
        if writer == "asset-edit":
            return assets.update("p", asset.id, name="Saved")
        if writer == "asset-delete":
            return assets.delete("p", asset.id)
        if writer == "asset-upload":
            return assets.import_bytes("p", "new.txt", b"new")
        if writer == "primary":
            return ResultService(factory).select_primary("p", "t0", "result")
        if writer == "review":
            return PromptReviewService(factory).approve("p", "t0")
        if writer == "revision":
            return PromptEnhancementService(factory, None, None, None).select_revision(
                "p", "t0", "revision",
            )
        if writer == "project":
            return ProjectService(factory, MediaStorage(tmp_path / "media")).update(
                "p", title="Saved",
            )
        if writer == "create":
            return TaskService(factory).create("p", SaveTaskData(title="Created"))
        if writer == "reorder":
            return TaskService(factory).reorder("p", ["t1", "t0"])
        if writer == "preference":
            return TaskService(factory).update_editor_preference("p", "t0", user_view_mode="text")
        return TaskService(factory).update("p", "t0", SaveTaskData(title="Saved"))

    def transition():
        if target == "project":
            return lifecycle_service.transition_project("p", action)
        return lifecycle_service.transition_tasks("p", ["t0"], action)

    with ThreadPoolExecutor(max_workers=2) as pool:
        leading = pool.submit(edit if first == "edit" else transition)
        assert entered.wait(5)
        following = pool.submit(transition if first == "edit" else edit)
        try:
            try:
                following.result(timeout=0.3)
            except (TimeoutError, ConflictError):
                pass
            finished_before_release = following.done()
        finally:
            release.set()
        leading.result(timeout=5)
        if first == "edit":
            following.result(timeout=5)
            assert not finished_before_release, "lifecycle bypassed an admitted edit transaction"
        else:
            with pytest.raises(ConflictError) as error:
                following.result(timeout=5)
            assert error.value.code == "OBJECT_READ_ONLY"
    with factory() as uow:
        if writer in {"task", "project"}:
            edited = uow.projects.get("p") if writer == "project" else uow.tasks.get("t0")
            assert edited.title == ("Saved" if first == "edit" else (
                "Project" if writer == "project" else "Task"
            ))
        elif writer == "create":
            assert len(uow.tasks.list_by_project("p")) == (3 if first == "edit" else 2)
        elif writer == "reorder":
            assert [task.id for task in uow.tasks.list_by_project("p")] == (
                ["t1", "t0"] if first == "edit" else ["t0", "t1"]
            )
        elif writer == "preference":
            assert uow.tasks.get("t0").user_view_mode == ("text" if first == "edit" else "visual")
        elif writer == "asset-edit":
            assert uow.assets.get(asset.id).name == ("Saved" if first == "edit" else "original")
        elif writer == "asset-delete":
            assert (uow.assets.get(asset.id) is None) == (first == "edit")
        elif writer == "asset-upload":
            remaining = uow.assets.list_by_project("p")
            assert len(remaining) == (2 if first == "edit" else 1)
            root = storage.project_root("p")
            assert {path.relative_to(root).as_posix() for path in root.rglob("*")
                    if path.is_file()} == {item.project_relative_path for item in remaining}
        elif writer == "primary":
            assert uow.tasks.get("t0").primary_result_id == ("result" if first == "edit" else None)
        elif writer == "review":
            assert (uow.tasks.get("t0").approved_at is not None) == (first == "edit")
        elif writer == "revision":
            assert uow.tasks.get("t0").ai_prompt == ("Selected prompt" if first == "edit" else "")
        changed = uow.projects.get("p") if target == "project" else uow.tasks.get("t0")
        assert getattr(changed, "archived_at" if action == "archive" else "deleted_at")
