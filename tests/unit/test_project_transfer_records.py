import json
from copy import deepcopy

import pytest
from shotmill.application.project_transfer_records import serialize_project_transfer_records
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.domain.entities import Job, Project, Result, Task
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError


def source_graph():
    task = Task("t", "p", 1, "Task", user_prompt="Keep my prompt")
    job = Job("j", "p", "t", JobStatus.COMPLETED, "Original", {}, [], {}, {
        "providerId": "comfyui", "workflowId": "video.json", "apiKey": "secret-key",
        "baseUrl": "http://private-server:8188", "workflowSnapshot": {"key": "secret-key"},
    }, {"seed": 42}, {})
    return ProjectTransferSource(
        Project("p", "Project"), [], [task], [], [], [job],
        [Result("r", "p", "t", "j", "/media/p/output.mp4", metadata={
            "contentType": "video/mp4", "relativePath": "C:/private/clip.mp4",
            "providerResponse": {"token": "secret-key"},
        })], [], [], [], [],
    )


def test_portable_records_preserve_creative_history_without_provider_configuration():
    source = source_graph()
    original = deepcopy(source)
    records = serialize_project_transfer_records(source)
    encoded = json.dumps(records)
    assert "secret-key" not in encoded
    assert "private-server" not in encoded
    assert "C:/private" not in encoded
    assert records["tasks"][0]["user_prompt"] == "Keep my prompt"
    assert records["jobs"][0]["final_prompt_snapshot"] == "Original"
    assert records["jobs"][0]["params_snapshot"] == {"seed": 42}
    assert records["jobs"][0]["status"] == "completed"
    assert records["providerRequirements"][0]["workflowId"] == "video.json"
    assert source == original


@pytest.mark.parametrize("params", [
    {"unknownCreativeSetting": 7}, {"seed": {"apiKey": "secret"}}, {"cfg": float("nan")},
])
def test_unsupported_parameters_fail_instead_of_silent_loss(params):
    source = source_graph()
    source.tasks[0].generation_params = params
    with pytest.raises(ConflictError):
        serialize_project_transfer_records(source)


def test_workflow_slots_and_context_media_relationships_survive_serialization():
    source = source_graph()
    selection = {"workflowId": "video.json", "slots": [
        {"portId": "3:image:7", "assetId": "a", "reference": "<Picture 1>"},
    ]}
    source.tasks[0].generation_params = {"workflowInputs": selection}
    media = {"assetId": "context-1", "sourceResultId": "r0", "sourceTaskId": "t0",
             "projectRelativePath": "context/frame.png", "sourceDurationSeconds": 6,
             "startSeconds": 5, "endSeconds": 6, "audioIncluded": False}
    source.jobs[0].execution_context = {"mode": "尾帧承接", "media": [media]}
    records = serialize_project_transfer_records(source)
    assert records["tasks"][0]["generation_params"]["workflowInputs"] == selection
    assert records["jobs"][0]["execution_context"]["media"] == [media]
