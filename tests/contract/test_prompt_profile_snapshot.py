from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from shotmill.domain.application_settings import LocalInferenceSettings, PromptSystemSettings
from shotmill.domain.providers import PromptAIRequest
from shotmill.errors import ShotMillError
from shotmill.providers.prompt_ai.comfyui import ComfyUIPromptAIProvider
from shotmill.providers.prompt_ai.configurable import ConfigurablePromptAIProvider
from shotmill.providers.prompt_ai.openai_compatible import OpenAICompatiblePromptAIProvider


def test_local_profile_freezes_endpoint_model_parameters_and_system_prompt():
    current = LocalInferenceSettings(max_frames=12, max_size=320, seed_mode="fixed", seed=17)
    system = PromptSystemSettings(system_prompt="original rules")
    url = "http://original.test"
    submitted = []

    async def handler(request):
        assert request.url.host == "original.test"
        if request.method == "POST":
            submitted.append(json.loads(request.content)["prompt"])
            return httpx.Response(200, json={"promptId": "p"})
        return httpx.Response(200, json={"status": "completed", "nodeOutputs": {"1": "done"}})

    local = ComfyUIPromptAIProvider(
        None, settings_getter=lambda: current, system_prompt_getter=lambda: system,
        base_url_getter=lambda: url, transport=httpx.MockTransport(handler),
    )
    configured = ConfigurablePromptAIProvider(local, local, lambda: system)
    profile = json.loads(json.dumps(configured.capture_profile()))
    current = replace(current, max_frames=99, max_size=768, seed=999)
    system = replace(system, provider_mode="api", system_prompt="changed rules")
    url = "http://changed.test"
    frozen = configured.bind_profile(profile)
    asyncio.run(frozen.enhance(PromptAIRequest(system_prompt="skill", user_text="text")))
    inputs = submitted[0]["1"]["inputs"]
    assert inputs["system_prompt"] == "original rules"
    assert (inputs["max_frames"], inputs["max_size"], inputs["seed"]) == (12, 320, 17)
    assert submitted[0]["3"]["inputs"]["model"] == profile["provider"]["modelInputs"]["model"]


def test_api_profile_freezes_effective_model_and_endpoint_without_persisting_key():
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    original = OpenAICompatiblePromptAIProvider(
        "http://old.test/v1", "old-model", "private-key", transport=httpx.MockTransport(handler)
    )
    profile = json.loads(json.dumps(original.capture_profile()))
    assert "private-key" not in json.dumps(profile)
    changed = OpenAICompatiblePromptAIProvider(
        "http://new.test/v1", "new-model", "private-key", transport=httpx.MockTransport(handler)
    )
    frozen = changed.bind_profile(profile)
    asyncio.run(frozen.enhance(PromptAIRequest(system_prompt="rules", user_text="text")))
    assert requests[0].url.host == "old.test"
    assert json.loads(requests[0].content)["model"] == "old-model"
    assert requests[0].headers["Authorization"] == "Bearer private-key"
    changed.api_key = "different-key"
    with pytest.raises(ShotMillError, match="凭据"):
        changed.bind_profile(profile)
