from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from shotmill.domain.application_settings import PromptSystemSettings
from shotmill.domain.providers import (
    PromptAIProvider,
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
)


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

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        settings = self.settings_getter()
        provider = self.local_provider
        if settings.provider_mode == "api":
            provider = (
                self.api_provider_factory(settings)
                if self.api_provider_factory is not None
                else self.api_provider
            )
        configured_request = replace(request, system_prompt=settings.system_prompt)
        return await provider.enhance(configured_request)
