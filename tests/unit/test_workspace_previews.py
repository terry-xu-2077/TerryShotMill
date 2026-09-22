from shotmill.domain.entities import Project, Result, Task, TaskAssetBinding
from shotmill.frontend_adapter.mapper import map_project_summary, map_task_summary


def task_with_references():
    return Task(id="task", project_id="project", display_order=1, title="Task", asset_bindings=[
        TaskAssetBinding("later", "<Picture 2>", order_index=2),
        TaskAssetBinding("sound", "<Audio 1>", order_index=0),
        TaskAssetBinding("first", "<Picture 1>", order_index=1),
    ])


def test_task_preview_uses_ordered_bound_media_without_a_result():
    task = task_with_references()
    view = map_task_summary(task, [], asset_previews={
        "later": "/later.png", "first": "/first.png", "sound": None,
        "unbound": "/unbound.png",
    })
    assert view.preview_url == "/first.png"
    assert view.result_count == 0
    assert view.primary_result is None
    assert view.status == "idle"


def test_task_does_not_borrow_an_unbound_asset():
    assert map_task_summary(task_with_references(), [], asset_previews={
        "unbound": "/unbound.png",
    }).preview_url is None


def test_primary_result_thumbnail_still_wins():
    task = task_with_references()
    task.primary_result_id = "result"
    result = Result(id="result", project_id="project", task_id="task", job_id="job",
                    video_url="/result.mp4", preview_url="/result.png")
    assert map_task_summary(task, [result], asset_previews={
        "first": "/first.png",
    }).preview_url == "/result.png"


def test_project_can_show_reference_cover_before_first_generation():
    view = map_project_summary(Project(id="project", title="Project"), [task_with_references()],
                               3, {}, asset_previews={"first": "/first.png"})
    assert view.cover_url == "/first.png"
    assert view.status == "idle"


def test_explicit_project_cover_is_respected_without_tasks():
    project = Project(id="project", title="Project", cover_asset_id="cover")
    assert map_project_summary(project, [], 2, {}, asset_previews={
        "other": "/other.png", "cover": "/cover.png",
    }).cover_url == "/cover.png"


def test_automatic_cover_follows_first_task_even_if_later_task_has_video():
    first = task_with_references()
    later = Task(id="later-task", project_id="project", display_order=2, title="Later")
    result = Result(id="r", project_id="project", task_id=later.id, job_id="j",
                    video_url="/later.mp4", preview_url="/later-result.png")
    view = map_project_summary(Project(id="project", title="Project"), [later, first],
                               3, {later.id: [result]}, asset_previews={"first": "/first.png"})
    assert view.cover_url == "/first.png"
