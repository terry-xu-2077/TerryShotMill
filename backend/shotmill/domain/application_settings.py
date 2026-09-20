from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shotmill.prompt_skills.minimax_h3_system_prompt import DEFAULT_H3_SYSTEM_PROMPT

InferenceMode = Literal["one by one", "images", "video"]
SeedMode = Literal["randomize", "fixed"]
PromptProviderMode = Literal["local", "api"]


@dataclass(frozen=True, slots=True)
class ComfyUIWorkflowProfile:
    id: str
    name: str
    resolution: str = ""
    quality: str = ""
    workflow_file: str = ""
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ComfyUISettings:
    base_url: str = "http://127.0.0.1:8188"
    root_path: str = ""
    workflow_directory: str = "user/default/workflows"
    default_profile_id: str = ""
    workflow_profiles: tuple[ComfyUIWorkflowProfile, ...] = ()


@dataclass(frozen=True, slots=True)
class SystemPromptPreset:
    id: str
    name: str
    prompt: str


DEFAULT_SYSTEM_PROMPT_PRESET = SystemPromptPreset(
    id="minimax-h3-default",
    name="MiniMax H3 默认",
    prompt=DEFAULT_H3_SYSTEM_PROMPT,
)


@dataclass(frozen=True, slots=True)
class PromptSystemSettings:
    provider_mode: PromptProviderMode = "local"
    system_prompt: str = DEFAULT_H3_SYSTEM_PROMPT
    system_prompt_presets: tuple[SystemPromptPreset, ...] = (DEFAULT_SYSTEM_PROMPT_PRESET,)
    api_base_url: str = ""
    api_model: str = ""
    api_key: str = ""
    api_supports_native_video: bool = False


@dataclass(frozen=True, slots=True)
class LocalInferenceSettings:
    """Persisted inputs owned by the llama_cpp_instruct_adv adapter."""

    preset_prompt: str = "Empty - Nothing"
    inference_mode: InferenceMode = "images"
    max_frames: int = 24
    max_size: int = 256
    seed_mode: SeedMode = "randomize"
    seed: int = 0
    force_offload: bool = False
    save_states: bool = False
