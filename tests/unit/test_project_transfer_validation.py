from copy import deepcopy

import pytest
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.application.project_transfer_validation import validate_project_transfer_graph
from shotmill.domain.entities import (
    ContextLink,
    Job,
    Project,
    Result,
    Scene,
    Task,
    TaskPlacement,
    utcnow,
)
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError


def graph():
    return ProjectTransferSource(
        Project("p", "Project"), [], [Task("t", "p", 1, "Task")], [Scene("s", "p")],
        [TaskPlacement("t", "s", 1)],
        [Job("j", "p", "t", JobStatus.COMPLETED, "Prompt", {}, [], {}, {}, {}, {})],
        [Result("r", "p", "t", "j", "/media/p/output.mp4")], [], [], [], [],
    )


def test_valid_graph_is_not_mutated():
    source = graph()
    original = deepcopy(source)
    validate_project_transfer_graph(source)
    assert source == original


@pytest.mark.parametrize("damage", [
    lambda s: s.tasks.append(deepcopy(s.tasks[0])),
    lambda s: setattr(s.results[0], "project_id", "other"),
    lambda s: setattr(s.results[0], "job_id", "missing"),
    lambda s: setattr(s.jobs[0], "task_id", "missing"),
    lambda s: setattr(s.jobs[0], "status", JobStatus.RUNNING),
    lambda s: setattr(s.tasks[0], "primary_result_id", "missing"),
    lambda s: s.placements.clear(),
    lambda s: s.placements.append(deepcopy(s.placements[0])),
    lambda s: setattr(s.placements[0], "scene_id", "missing"),
])
def test_invalid_graph_rejected_before_publication(damage):
    source = graph()
    damage(source)
    with pytest.raises(ConflictError):
        validate_project_transfer_graph(source)


def test_missing_context_source_requires_tombstone_and_must_not_rebind():
    source = graph()
    link = ContextLink("c", "p", "gone", "t", "last-frame")
    source.contexts = [link]
    with pytest.raises(ConflictError):
        validate_project_transfer_graph(source)
    link.source_deleted_at = utcnow()
    validate_project_transfer_graph(source)
    source.tasks.append(Task("gone", "p", 2, "Wrong replacement"))
    source.placements.append(TaskPlacement("gone", "s", 2))
    with pytest.raises(ConflictError):
        validate_project_transfer_graph(source)
