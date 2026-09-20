from dataclasses import replace
from types import SimpleNamespace

import pytest
from shotmill.application.container import build_container
from shotmill.config import Settings
from shotmill.domain.application_settings import ComfyUISettings, ComfyUIWorkflowProfile
from shotmill.errors import ShotMillError


def test_video_provider_honors_selected_workflow_and_rejects_unavailable_profiles(tmp_path):
    container = build_container(Settings(
        app_name="ShotMill", api_version="0.3", data_root=tmp_path,
        database_url="sqlite+pysqlite:///:memory:",
    ))
    store = container.application_settings
    configured = ComfyUISettings(default_profile_id="standard", workflow_profiles=(
        ComfyUIWorkflowProfile(id="standard", name="Standard", workflow_file="standard.json"),
        ComfyUIWorkflowProfile(id="detail", name="Detail", workflow_file="detail.json"),
    ))
    try:
        def update(value):
            store.update(local_inference=store.get_local_inference(),
                         prompt_system=store.get_prompt_system(), comfyui=value)

        update(configured)
        provider = container.generation_service.provider
        request = SimpleNamespace(params={"workflowProfileId": "detail"})
        assert provider._load_workflow_id(request) == "detail.json"
        assert provider._load_workflow_id(SimpleNamespace(params={})) == "standard.json"
        for profiles in (
            (configured.workflow_profiles[0],),
            (
                configured.workflow_profiles[0],
                replace(configured.workflow_profiles[1], enabled=False),
            ),
            (
                configured.workflow_profiles[0],
                replace(configured.workflow_profiles[1], workflow_file=""),
            ),
        ):
            update(replace(configured, workflow_profiles=profiles))
            with pytest.raises(ShotMillError, match="工作流"):
                provider._load_workflow_id(request)
    finally:
        container.engine.dispose()
