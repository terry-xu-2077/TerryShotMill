import pytest
from shotmill.domain.application_settings import WorkflowNumericBinding
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.numeric_bindings import resolve_numeric_bindings

PORTS = [{"type": "INT", "targetNodeId": "7", "targetPort": "frames", "sourceNodeId": "2"},
         {"type": "FLOAT", "targetNodeId": "7", "targetPort": "seconds", "sourceNodeId": "3"}]


def test_duration_and_aligned_frames_resolve_without_changing_input():
    bindings = (
        WorkflowNumericBinding(
            "7:frames:2", "frameCount", fps=24, frame_multiple=4, frame_offset=1
        ),
        WorkflowNumericBinding("7:seconds:3", "durationSeconds"),
    )
    assert resolve_numeric_bindings(bindings, PORTS, 6) == {"7:frames:2": 145, "7:seconds:3": 6}
    assert resolve_numeric_bindings(bindings, PORTS, 6.5) == {"7:frames:2": 157, "7:seconds:3": 6.5}


@pytest.mark.parametrize("binding", [
    WorkflowNumericBinding("missing", "constant", value=2),
    WorkflowNumericBinding("7:frames:2", "constant", value=2.5),
    WorkflowNumericBinding("7:frames:2", "constant", value=float("nan")),
    WorkflowNumericBinding("7:frames:2", "frameCount", fps=0),
    WorkflowNumericBinding("7:frames:2", "frameCount", frame_multiple=0),
])
def test_invalid_or_stale_numeric_bindings_fail_before_submission(binding):
    with pytest.raises(ShotMillError):
        resolve_numeric_bindings((binding,), PORTS, 6)


def test_duplicate_port_binding_is_rejected():
    binding = WorkflowNumericBinding("7:frames:2", "constant", value=12)
    with pytest.raises(ShotMillError):
        resolve_numeric_bindings((binding, binding), PORTS, 6)
