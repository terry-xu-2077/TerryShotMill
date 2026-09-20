from __future__ import annotations

import asyncio

from shotmill.domain.application_settings import PromptSystemSettings
from shotmill.domain.providers import (
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
)
from shotmill.providers.prompt_ai.configurable import ConfigurablePromptAIProvider


class _FakeProvider:
    capability = PromptAIProviderCapability()

    def __init__(self, provider_id: str) -> None:
        self.id = provider_id
        self.requests: list[PromptAIRequest] = []

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        self.requests.append(request)
        return PromptAIResponse(text=self.id, provider_id=self.id)


def test_configurable_prompt_provider_switches_mode_and_uses_common_system_prompt() -> None:
    asyncio.run(_run_test())


async def _run_test() -> None:
    current = PromptSystemSettings(
        provider_mode="local",
        system_prompt="configured system prompt",
    )
    local = _FakeProvider("local")
    api = _FakeProvider("api")
    provider = ConfigurablePromptAIProvider(local, api, lambda: current)
    request = PromptAIRequest(system_prompt="skill default", user_text="user text")

    assert (await provider.enhance(request)).provider_id == "local"
    assert local.requests[-1].system_prompt == "configured system prompt"

    current = PromptSystemSettings(
        provider_mode="api",
        system_prompt="configured system prompt",
    )
    assert (await provider.enhance(request)).provider_id == "api"
    assert api.requests[-1].system_prompt == "configured system prompt"
