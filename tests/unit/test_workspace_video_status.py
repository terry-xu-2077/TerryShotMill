import pytest
from shotmill.domain.entities import Task
from shotmill.domain.enums import TaskState
from shotmill.frontend_adapter.mapper import map_task_summary


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (TaskState.QUEUED, "queued"),
        (TaskState.RUNNING, "running"),
        (TaskState.COMPLETED, "completed"),
        (TaskState.FAILED, "failed"),
        (TaskState.PROMPT_GENERATING, "idle"),
        (TaskState.READY, "idle"),
    ],
)
def test_video_status_distinguishes_waiting_from_generation(state, expected):
    task = Task(id="task", project_id="project", display_order=1, title="Task", state=state)
    view = map_task_summary(task, [])
    assert view.video_generation_status == expected
    if state == TaskState.QUEUED:
        assert view.status == "running"
