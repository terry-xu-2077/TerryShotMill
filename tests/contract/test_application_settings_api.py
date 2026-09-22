from __future__ import annotations

import httpx


def test_prompt_label_uses_effective_provider_and_model(client):
    from dataclasses import replace

    from shotmill.domain.application_settings import PromptSystemSettings
    from shotmill.providers.prompt_ai.comfyui import ComfyUIPromptAIProvider
    from shotmill.providers.prompt_ai.configurable import ConfigurablePromptAIProvider
    from shotmill.providers.prompt_ai.openai_compatible import OpenAICompatiblePromptAIProvider

    local = ComfyUIPromptAIProvider("http://local.test")
    local.model_inputs["model"] = "local-selected.gguf"
    api = OpenAICompatiblePromptAIProvider("http://api.test/v1", "environment-model")
    settings = PromptSystemSettings()
    provider = ConfigurablePromptAIProvider(local, api, lambda: settings)
    client.app.state.container.prompt_enhancement_service.provider = provider

    def label():
        response = client.get("/api/v1/application/settings")
        assert response.status_code == 200
        return response.json()["promptAiLabel"]

    assert label() == "本地 · local-selected.gguf"
    settings = replace(settings, provider_mode="api")
    assert label() == "API · environment-model"
    provider.api_provider_factory = lambda value: OpenAICompatiblePromptAIProvider(
        "http://api.test/v1", value.api_model or "environment-model"
    )
    settings = replace(settings, api_model="configured-model")
    assert label() == "API · configured-model"


def test_workflow_catalog_timeout_is_not_an_empty_success(client, monkeypatch):
    from shotmill.api import comfyui

    async def catalog(_settings):
        raise httpx.ReadTimeout("busy")

    monkeypatch.setattr(comfyui, "fetch_bridge_workflows", catalog)
    response = client.get("/api/v1/comfyui/workflows")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "WORKFLOW_CATALOG_UNAVAILABLE"


def test_workflow_catalog_preserves_bridge_port_metadata(client, monkeypatch):
    from shotmill.api import comfyui

    port = {
        "name": "image 1",
        "direction": "input",
        "type": "IMAGE",
        "sourceNodeId": "12",
        "targetNodeId": "42",
        "targetSlot": "0",
        "targetPort": "image_0",
        "portName": "image_0",
    }

    async def catalog(_settings):
        return [
            {
                "id": "test.json",
                "name": "test",
                "fileName": "test.json",
                "relativePath": "test.json",
                "format": "canvas",
                "executable": True,
                "hasShotmillBridge": True,
                "inputs": [port],
                "outputs": [],
                "warnings": [],
            }
        ]

    monkeypatch.setattr(comfyui, "fetch_bridge_workflows", catalog)
    response = client.get("/api/v1/comfyui/workflows")
    assert response.status_code == 200
    assert response.json()[0]["inputs"][0] == port


def test_application_settings_are_read_and_persisted(client) -> None:
    initial = client.get("/api/v1/application/settings")
    assert initial.status_code == 200
    assert initial.json()["localInference"]["maxSize"] == 256

    updated = client.patch(
        "/api/v1/application/settings",
        json={
            "providerMode": "local",
            "systemPrompt": "Rewrite into a structured H3 prompt.",
            "systemPromptPresets": [
                {
                    "id": "test-preset",
                    "name": "测试预设",
                    "prompt": "Rewrite into a structured H3 prompt.",
                }
            ],
            "apiBaseUrl": "http://api.test/v1",
            "apiModel": "test-model",
            "apiKey": "secret",
            "apiSupportsNativeVideo": False,
            "localInference": {
                "presetPrompt": "Normal - Describe",
                "inferenceMode": "images",
                "maxFrames": 48,
                "maxSize": 512,
                "seedMode": "fixed",
                "seed": 42,
                "forceOffload": True,
                "saveStates": False,
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["localInference"]["maxSize"] == 512
    assert updated.json()["localInference"]["forceOffload"] is True
    assert updated.json()["systemPrompt"] == "Rewrite into a structured H3 prompt."
    assert updated.json()["systemPromptPresets"][0]["name"] == "测试预设"

    reread = client.get("/api/v1/application/settings")
    assert reread.json()["localInference"]["seed"] == 42
    assert reread.json()["apiModel"] == "test-model"


def test_workflow_preset_name_description_and_selection_survive_store_reload(client):
    from shotmill.application.application_settings import ApplicationSettingsStore

    settings = client.get("/api/v1/application/settings").json()
    settings["comfyui"]["workflowProfiles"] = [
        {
            "id": "cinema",
            "name": "电影质感",
            "description": "人物近景与低速运镜",
            "workflowFile": "cinema.json",
            "enabled": True,
            "numericBindings": [
                {
                    "portId": "7:frames:2",
                    "source": "frameCount",
                    "fps": 24,
                    "frameMultiple": 4,
                    "frameOffset": 1,
                }
            ],
        }
    ]
    settings["comfyui"]["defaultProfileId"] = "cinema"
    saved = client.patch("/api/v1/application/settings", json=settings)
    assert saved.status_code == 200, saved.text
    assert saved.json()["comfyui"]["workflowProfiles"][0]["description"] == "人物近景与低速运镜"
    reloaded = ApplicationSettingsStore(client.app.state.container.application_settings.path)
    profile = reloaded.get_comfyui().workflow_profiles[0]
    assert (profile.name, profile.description, profile.workflow_file) == (
        "电影质感",
        "人物近景与低速运镜",
        "cinema.json",
    )
    assert reloaded.get_comfyui().default_profile_id == "cinema"
    binding = profile.numeric_bindings[0]
    assert (binding.port_id, binding.source, binding.fps, binding.frame_multiple) == (
        "7:frames:2",
        "frameCount",
        24,
        4,
    )


def test_language_presets_can_be_selected_and_saved(client):
    settings = client.get("/api/v1/application/settings").json()
    presets = settings["systemPromptPresets"]
    assert [p["name"] for p in presets] == ["MiniMax H3 · 英文输出", "MiniMax H3 · 中文输出"]
    for preset in presets:
        settings["systemPrompt"] = preset["prompt"]
        response = client.patch("/api/v1/application/settings", json=settings)
        assert response.status_code == 200
        saved = client.get("/api/v1/application/settings").json()
        assert saved["systemPrompt"] == preset["prompt"]
        assert saved["systemPromptPresets"] == presets
