from __future__ import annotations

import httpx


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
        "name": "image 1", "direction": "input", "type": "IMAGE",
        "sourceNodeId": "12", "targetNodeId": "42", "targetSlot": "0",
        "targetPort": "image_0", "portName": "image_0",
    }

    async def catalog(_settings):
        return [{
            "id": "test.json", "name": "test", "fileName": "test.json",
            "relativePath": "test.json", "format": "canvas", "executable": True,
            "hasShotmillBridge": True, "inputs": [port], "outputs": [], "warnings": [],
        }]

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
            "systemPromptPresets": [{
                "id": "test-preset",
                "name": "测试预设",
                "prompt": "Rewrite into a structured H3 prompt.",
            }],
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
            }
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
