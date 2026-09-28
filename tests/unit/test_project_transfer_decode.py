from copy import deepcopy

import pytest
from shotmill.application.project_transfer_decode import decode_project_transfer_records
from shotmill.application.project_transfer_records import serialize_project_transfer_records
from shotmill.errors import ConflictError
from test_project_transfer_validation import graph


def test_exported_records_decode_without_mutation():
    source = graph()
    records = serialize_project_transfer_records(source)
    original = deepcopy(records)
    decoded = decode_project_transfer_records(records)
    assert decoded.source == source
    assert records == original


def test_task_workflow_requirement_survives_decode():
    source = graph()
    source.tasks[0].generation_params = {"workflowProfileId": "desktop-profile"}
    records = serialize_project_transfer_records(source)
    decoded = decode_project_transfer_records(records)
    assert {"kind": "video", "requiresConfiguration": True,
            "workflowProfileId": "desktop-profile"} in decoded.provider_requirements


@pytest.mark.parametrize("change", [
    lambda r: r.update(schemaVersion=True),
    lambda r: r.update(schemaVersion=2),
    lambda r: r.update(extra="ignored?"),
    lambda r: r["project"].update(extra="ignored?"),
    lambda r: r["tasks"][0].pop("title"),
    lambda r: r["tasks"][0].update(display_order="1"),
    lambda r: r["tasks"][0].update(display_order=True),
    lambda r: r["jobs"][0].update(status="invented"),
    lambda r: r["jobs"][0].update(provider_profile_snapshot={"baseUrl": "http://attacker"}),
    lambda r: r["providerRequirements"].append({
        "kind": "video", "requiresConfiguration": True, "workflowId": "C:/private/file",
    }),
    lambda r: r["providerRequirements"].append({
        "kind": "video", "requiresConfiguration": True, "apiKey": "secret",
    }),
    lambda r: r["providerRequirements"].append({"kind": [], "requiresConfiguration": True}),
    lambda r: r["providerRequirements"].append({
        "kind": "video", "requiresConfiguration": True, "workflowProfileId": "C:/private/profile",
    }),
    lambda r: r["jobs"][0].update(assets_snapshot=[{"assetId": "missing-path"}]),
    lambda r: r["jobs"][0].update(context_snapshot={"media": [{}]}),
    lambda r: r["jobs"][0].update(execution_context={"media": [{}]}),
])
def test_malformed_or_executable_records_are_rejected(change):
    records = serialize_project_transfer_records(graph())
    change(records)
    with pytest.raises(ConflictError):
        decode_project_transfer_records(records)
