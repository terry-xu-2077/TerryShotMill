import httpx
import pytest


@pytest.mark.parametrize("health,connected,state", [
    ("healthy", True, "connected"),
    ("missing", True, "missing"),
    ("failure", True, "error"),
    ("timeout", True, "error"),
    ("invalid", True, "error"),
    ("offline", False, "disconnected"),
])
def test_status_distinguishes_comfyui_connection_from_bridge_health(
    client, monkeypatch, health, connected, state
):
    from shotmill.api import comfyui

    requested = []

    async def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/system_stats":
            return httpx.Response(503 if health == "offline" else 200, json={})
        if health == "timeout":
            raise httpx.ReadTimeout("Bridge busy")
        if health == "invalid":
            return httpx.Response(200, text="<html>wrong service</html>")
        return httpx.Response(
            404 if health == "missing" else 503 if health == "failure" else 200,
            json={"ok": health == "healthy", "package": "ComfyUI-ShotMill"},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(comfyui.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs
    ))
    response = client.get("/api/v1/comfyui/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is connected
    assert data["bridgeState"] == state
    assert data["bridgeNodeAvailable"] is (state == "connected")
    assert not any("workflows" in path for path in requested)
