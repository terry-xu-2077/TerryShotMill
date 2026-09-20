from __future__ import annotations

from typing import Literal

from pydantic import Field

from shotmill.frontend_adapter.models import (
    ApiModel,
    EditorPreference,
    GenerationSettings,
    TaskAssetRef,
)


class ProjectCreateRequest(ApiModel):
    title: str
    description: str = ""
    use_description_for_ai_prompt: bool = False


class SystemPromptPresetPayload(ApiModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1)


class ComfyUIWorkflowProfilePayload(ApiModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    resolution: str = ""
    quality: str = ""
    workflow_file: str = ""
    enabled: bool = True


class ComfyUISettingsPayload(ApiModel):
    base_url: str = "http://127.0.0.1:8188"
    root_path: str = ""
    workflow_directory: str = "user/default/workflows"
    default_profile_id: str = ""
    workflow_profiles: list[ComfyUIWorkflowProfilePayload] = []


class LocalInferenceSettingsPayload(ApiModel):
    preset_prompt: str = "Empty - Nothing"
    inference_mode: Literal["one by one", "images", "video"] = "images"
    max_frames: int = Field(default=24, ge=2, le=1024)
    max_size: int = Field(default=256, ge=128, le=16384)
    seed_mode: Literal["randomize", "fixed"] = "randomize"
    seed: int = Field(default=0, ge=0, le=0xFFFFFFFFFFFFFFFF)
    force_offload: bool = False
    save_states: bool = False


class ApplicationSettingsPatch(ApiModel):
    provider_mode: Literal["local", "api"] = "local"
    system_prompt: str = Field(min_length=1)
    system_prompt_presets: list[SystemPromptPresetPayload] = []
    api_base_url: str = ""
    api_model: str = ""
    api_key: str = ""
    api_supports_native_video: bool = False
    local_inference: LocalInferenceSettingsPayload
    comfyui: ComfyUISettingsPayload = ComfyUISettingsPayload()


class ProjectPatchRequest(ApiModel):
    title: str | None = None
    description: str | None = None
    use_description_for_ai_prompt: bool | None = None


class AssetPatchRequest(ApiModel):
    name: str | None = None
    category: str | None = None
    tags: list[str] | None = None


class TaskSaveRequest(ApiModel):
    title: str
    summary: str = ""
    script_source: str = ""
    user_intent: str = ""
    user_prompt: str = ""
    ai_enhanced_prompt: str = ""
    prompt_source: Literal["user", "ai"] = "user"
    duration_seconds: float = Field(default=6.0, gt=0)
    generation: GenerationSettings = GenerationSettings()
    asset_bindings: list[TaskAssetRef] = []
    editor_preference: EditorPreference = EditorPreference()
    revision: int | None = None


class TaskReorderRequest(ApiModel):
    task_ids: list[str]


class PromptEnhancementMediaRequest(ApiModel):
    asset_id: str
    reference: str
    role: str | None = None


class PromptEnhancementContextRequest(ApiModel):
    include_project_background: bool = False
    include_previous_task_summary: bool = False


class PromptEnhancementGenerationRequest(ApiModel):
    duration_seconds: float = Field(gt=0)
    mode: str
    context_mode: str | None = None


class PromptEnhancementRequest(ApiModel):
    target: str
    user_prompt: str
    media: list[PromptEnhancementMediaRequest] = []
    context: PromptEnhancementContextRequest = PromptEnhancementContextRequest()
    generation: PromptEnhancementGenerationRequest


class PromptEnhancementPreviewRequest(PromptEnhancementRequest):
    previous_task_id: str | None = None


class GenerationSubmitRequest(ApiModel):
    seed: int | None = None


class PrimaryResultRequest(ApiModel):
    result_id: str


class BatchPromptEnhancementRequest(ApiModel):
    task_ids: list[str] = []
    include_project_background: bool = False
    include_previous_task_summary: bool = False


class VideoBatchRequest(ApiModel):
    task_ids: list[str] = []
