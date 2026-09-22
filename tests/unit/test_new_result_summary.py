from shotmill.domain.entities import Result, Task
from shotmill.frontend_adapter.mapper import map_task_summary


def test_new_result_is_independent_of_primary_result_and_task_status():
    task = Task(id="t", project_id="p", display_order=1, title="Task")
    assert map_task_summary(task, []).latest_video_result_id is None
    task.primary_result_id = "old"
    results = [Result(id=key, project_id="p", task_id="t", job_id=key,
                      video_url=f"/{key}.mp4") for key in ["new", "old"]]
    view = map_task_summary(task, results)
    assert view.latest_video_result_id == "new"
    assert view.primary_result.id == "old"
