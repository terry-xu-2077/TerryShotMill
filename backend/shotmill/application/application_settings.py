from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from shotmill.domain.application_settings import (
    DEFAULT_SYSTEM_PROMPT_PRESET,
    ComfyUISettings,
    ComfyUIWorkflowProfile,
    LocalInferenceSettings,
    PromptSystemSettings,
    SystemPromptPreset,
)


class ApplicationSettingsStore:
    """Small JSON-backed store for low-frequency application settings."""

    def __init__(self, path: Path, *, comfyui_defaults: ComfyUISettings | None = None) -> None:
        self.path = path
        self._comfyui_defaults = comfyui_defaults or ComfyUISettings()
        self._local_inference = self._read_local_inference()
        self._prompt_system = self._read_prompt_system()
        self._comfyui = self._read_comfyui()

    def get_local_inference(self) -> LocalInferenceSettings:
        return self._local_inference

    def get_prompt_system(self) -> PromptSystemSettings:
        return self._prompt_system

    def get_comfyui(self) -> ComfyUISettings:
        return self._comfyui

    def update(
        self,
        *,
        local_inference: LocalInferenceSettings,
        prompt_system: PromptSystemSettings,
        comfyui: ComfyUISettings | None = None,
    ) -> None:
        self._local_inference = local_inference
        self._prompt_system = prompt_system
        if comfyui is not None:
            self._comfyui = comfyui
        self._write()

    def update_local_inference(self, settings: LocalInferenceSettings) -> LocalInferenceSettings:
        self._local_inference = settings
        self._write()
        return settings

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "prompt_system": asdict(self._prompt_system),
                    "local_inference": asdict(self._local_inference),
                    "comfyui": asdict(self._comfyui),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _read_local_inference(self) -> LocalInferenceSettings:
        if not self.path.exists():
            return LocalInferenceSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            values = raw.get("local_inference", {}) if isinstance(raw, dict) else {}
            if not isinstance(values, dict):
                return LocalInferenceSettings()
            base = LocalInferenceSettings()
            return LocalInferenceSettings(
                preset_prompt=str(values.get("preset_prompt", base.preset_prompt)),
                inference_mode=values.get("inference_mode", base.inference_mode),
                max_frames=int(values.get("max_frames", base.max_frames)),
                max_size=int(values.get("max_size", base.max_size)),
                seed_mode=values.get("seed_mode", base.seed_mode),
                seed=int(values.get("seed", base.seed)),
                force_offload=bool(values.get("force_offload", base.force_offload)),
                save_states=bool(values.get("save_states", base.save_states)),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return LocalInferenceSettings()

    def _read_prompt_system(self) -> PromptSystemSettings:
        if not self.path.exists():
            return PromptSystemSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            values = raw.get("prompt_system", {}) if isinstance(raw, dict) else {}
            if not isinstance(values, dict):
                values = {}
            # Migrate the short-lived nested shape created before system_prompt became common.
            legacy = raw.get("local_inference", {}) if isinstance(raw, dict) else {}
            if not values and isinstance(legacy, dict):
                values = legacy
            presets = tuple(
                SystemPromptPreset(
                    id=str(item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    prompt=str(item.get("prompt") or ""),
                )
                for item in values.get("system_prompt_presets", [])
                if isinstance(item, dict)
                and str(item.get("id") or "").strip()
                and str(item.get("name") or "").strip()
                and str(item.get("prompt") or "").strip()
            )
            base = PromptSystemSettings()
            return PromptSystemSettings(
                provider_mode=values.get("provider_mode", base.provider_mode),
                system_prompt=str(values.get("system_prompt") or base.system_prompt),
                system_prompt_presets=presets or (DEFAULT_SYSTEM_PROMPT_PRESET,),
                api_base_url=str(values.get("api_base_url") or base.api_base_url),
                api_model=str(values.get("api_model") or base.api_model),
                api_key=str(values.get("api_key") or base.api_key),
                api_supports_native_video=bool(
                    values.get("api_supports_native_video", base.api_supports_native_video)
                ),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return PromptSystemSettings()

    def _read_comfyui(self) -> ComfyUISettings:
        if not self.path.exists():
            return self._comfyui_defaults
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            values = raw.get("comfyui", {}) if isinstance(raw, dict) else {}
            if not isinstance(values, dict):
                return self._comfyui_defaults
            base = self._comfyui_defaults
            profiles = tuple(
                ComfyUIWorkflowProfile(
                    id=str(item.get("id") or ""),
                    name=str(item.get("name") or ""),
                    resolution=str(item.get("resolution") or ""),
                    quality=str(item.get("quality") or ""),
                    workflow_file=str(item.get("workflow_file") or ""),
                    enabled=bool(item.get("enabled", True)),
                )
                for item in values.get("workflow_profiles", [])
                if isinstance(item, dict)
                and str(item.get("id") or "").strip()
                and str(item.get("name") or "").strip()
            )
            return ComfyUISettings(
                base_url=str(values.get("base_url") or base.base_url),
                root_path=str(values.get("root_path") or base.root_path),
                workflow_directory=str(
                    values.get("workflow_directory") or base.workflow_directory
                ),
                default_profile_id=str(
                    values.get("default_profile_id") or base.default_profile_id
                ),
                workflow_profiles=profiles,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return self._comfyui_defaults
