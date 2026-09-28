from copy import deepcopy
from types import SimpleNamespace

import pytest
from shotmill.application.project_transfer_requirements import portable_provider_requirements


def test_dependency_descriptions_exclude_machine_and_secret_configuration():
    profile = {
        "providerId": "comfyui", "workflowId": "video/workflow.json",
        "baseUrl": "http://secret-server:8188", "apiKey": "secret",
        "credentialFingerprint": "secret-hash", "headers": {"Authorization": "secret"},
        "workflowSnapshot": {"nodes": {"api_key": "secret"}},
        "modelInputs": {"path": "C:/private/model"},
        "localInference": {"path": "C:/private/runtime"},
    }
    original = deepcopy(profile)
    job = SimpleNamespace(provider_profile_snapshot=profile)
    prompt = SimpleNamespace(provider_profile_snapshot={
        "providerId": "openai-compatible", "modelId": "org/model", "apiKey": "secret",
    })
    requirements = portable_provider_requirements(SimpleNamespace(
        jobs=[job, job], prompt_jobs=[prompt], tasks=[],
    ))
    assert requirements == [
        {"kind": "video", "requiresConfiguration": True,
         "providerId": "comfyui", "workflowId": "video/workflow.json"},
        {"kind": "prompt", "requiresConfiguration": True,
         "providerId": "openai-compatible", "modelId": "org/model"},
    ]
    assert profile == original


@pytest.mark.parametrize("value", [
    "C:/private/workflow.json", "C:\\private\\workflow.json", "/home/user/workflow.json",
    "../workflow.json", "https://server/private?token=secret", "//server/share/file",
])
def test_machine_locations_never_become_portable_identifiers(value):
    job = SimpleNamespace(provider_profile_snapshot={
        "providerId": value, "workflowId": value, "modelId": value,
    })
    source = SimpleNamespace(jobs=[job], prompt_jobs=[], tasks=[])
    assert portable_provider_requirements(source) == [
        {"kind": "video", "requiresConfiguration": True},
    ]


def test_ungenerated_tasks_keep_workflow_requirements_without_configuration():
    params = {"workflowProfileId": "desktop-profile", "workflowInputs": {
        "workflowId": "video/workflow.json", "slots": [{"assetId": "a", "portId": "1"}],
    }}
    original = deepcopy(params)
    task = SimpleNamespace(generation_params=params)
    source = SimpleNamespace(jobs=[], prompt_jobs=[], tasks=[task, task])
    assert portable_provider_requirements(source) == [{
        "kind": "video", "requiresConfiguration": True,
        "workflowProfileId": "desktop-profile", "workflowId": "video/workflow.json",
    }]
    assert params == original


def test_legacy_task_profile_and_machine_paths_are_handled():
    source = SimpleNamespace(jobs=[], prompt_jobs=[], tasks=[
        SimpleNamespace(generation_params={"profileId": "legacy-profile"}),
        SimpleNamespace(generation_params={"workflowProfileId": "C:/private/profile"}),
        SimpleNamespace(generation_params={}),
    ])
    assert portable_provider_requirements(source) == [
        {"kind": "video", "requiresConfiguration": True, "workflowProfileId": "legacy-profile"},
        {"kind": "video", "requiresConfiguration": True},
    ]
