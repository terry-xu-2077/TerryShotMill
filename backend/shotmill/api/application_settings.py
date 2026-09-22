from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import ApplicationSettingsPatch
from shotmill.domain.application_settings import (
    ComfyUISettings,
    ComfyUIWorkflowProfile,
    LocalInferenceSettings,
    PromptSystemSettings,
    SystemPromptPreset,
    WorkflowNumericBinding,
)
from shotmill.frontend_adapter.models import ApplicationSettingsView

router = APIRouter(prefix="/application", tags=["application-settings"])


def _view(container: ContainerDep) -> ApplicationSettingsView:
    local_inference = container.application_settings.get_local_inference()
    prompt_system = container.application_settings.get_prompt_system()
    return ApplicationSettingsView(
        prompt_ai_label=getattr(
            container.prompt_enhancement_service.provider, "display_name", "AI 增强服务"
        ),
        provider_mode=prompt_system.provider_mode,
        system_prompt=prompt_system.system_prompt,
        system_prompt_presets=[asdict(item) for item in prompt_system.system_prompt_presets],
        api_base_url=prompt_system.api_base_url,
        api_model=prompt_system.api_model,
        api_key=prompt_system.api_key,
        api_supports_native_video=prompt_system.api_supports_native_video,
        local_inference=asdict(local_inference),
        comfyui=asdict(container.application_settings.get_comfyui()),
    )


@router.get("/settings", response_model=ApplicationSettingsView)
def get_application_settings(container: ContainerDep) -> ApplicationSettingsView:
    return _view(container)


@router.patch("/settings", response_model=ApplicationSettingsView)
def update_application_settings(
    payload: ApplicationSettingsPatch,
    container: ContainerDep,
) -> ApplicationSettingsView:
    local_values = payload.local_inference.model_dump()
    container.application_settings.update(
        local_inference=LocalInferenceSettings(**local_values),
        prompt_system=PromptSystemSettings(
            provider_mode=payload.provider_mode,
            system_prompt=payload.system_prompt,
            system_prompt_presets=tuple(
                SystemPromptPreset(**item.model_dump()) for item in payload.system_prompt_presets
            ),
            api_base_url=payload.api_base_url,
            api_model=payload.api_model,
            api_key=payload.api_key,
            api_supports_native_video=payload.api_supports_native_video,
        ),
        comfyui=ComfyUISettings(
            base_url=payload.comfyui.base_url,
            root_path=payload.comfyui.root_path,
            workflow_directory=payload.comfyui.workflow_directory,
            default_profile_id=payload.comfyui.default_profile_id,
            workflow_profiles=tuple(
                ComfyUIWorkflowProfile(
                    **item.model_dump(exclude={"numeric_bindings"}),
                    numeric_bindings=tuple(
                        WorkflowNumericBinding(**binding.model_dump())
                        for binding in item.numeric_bindings
                    ),
                )
                for item in payload.comfyui.workflow_profiles
            ),
        ),
    )
    return _view(container)
