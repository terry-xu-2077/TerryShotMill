from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from shotmill.domain.application_settings import PromptSystemSettings
from shotmill.domain.providers import (
    PromptAIProvider,
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
    SnapshotPromptAIProvider,
)
from shotmill.errors import ShotMillError


class ConfigurablePromptAIProvider:
    """Selects local ComfyUI or API inference from application settings per request."""

    id = "configurable-prompt-ai"
    capability = PromptAIProviderCapability(
        image_input=True,
        native_video_input=True,
        sampled_video_frames=True,
        audio_understanding=False,
        system_prompt=True,
        structured_output=False,
    )

    def __init__(
        self,
        local_provider: PromptAIProvider,
        api_provider: PromptAIProvider,
        settings_getter: Callable[[], PromptSystemSettings],
        api_provider_factory: Callable[[PromptSystemSettings], PromptAIProvider] | None = None,
    ) -> None:
        self.local_provider = local_provider
        self.api_provider = api_provider
        self.settings_getter = settings_getter
        self.api_provider_factory = api_provider_factory

    def _selected_provider(self, settings: PromptSystemSettings) -> PromptAIProvider:
        if settings.provider_mode == "api":
            return (
                self.api_provider_factory(settings)
                if self.api_provider_factory
                else self.api_provider
            )
        return self.local_provider

    @property
    def display_name(self) -> str:
        selected = self._selected_provider(self.settings_getter())
        return getattr(selected, "display_name", "AI 增强服务")

    def capture_profile(self) -> dict[str, Any]:
        settings = self.settings_getter()
        selected = self._selected_provider(settings)
        provider = (
            selected.capture_profile()
            if isinstance(selected, SnapshotPromptAIProvider)
            else {"providerId": selected.id}
        )
        return {
            "version": 1,
            "providerId": self.id,
            "mode": settings.provider_mode,
            "systemPrompt": settings.system_prompt,
            "provider": provider,
        }

    def bind_profile(self, profile: dict[str, Any]) -> PromptAIProvider:
        if profile.get("version") != 1 or "provider" not in profile:
            raise ShotMillError(
                "PROMPT_PROFILE_SNAPSHOT_MISSING", "旧增强任务缺少完整配置，请重新提交增强。", 409
            )
        current = self.settings_getter()
        selected = self._selected_provider(replace(current, provider_mode=profile["mode"]))
        saved = profile["provider"]
        if saved.get("providerId") != selected.id:
            raise ShotMillError("PROMPT_PROFILE_UNAVAILABLE", "原增强服务不可用，请检查设置。", 409)
        if isinstance(selected, SnapshotPromptAIProvider):
            selected = selected.bind_profile(saved)
        frozen = PromptSystemSettings(system_prompt=profile["systemPrompt"])
        return ConfigurablePromptAIProvider(selected, selected, lambda: frozen)

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        settings = self.settings_getter()
        provider = self._selected_provider(settings)
        configured_request = replace(request, system_prompt=settings.system_prompt)
        return await provider.enhance(configured_request)
