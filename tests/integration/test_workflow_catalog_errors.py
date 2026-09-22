import httpx
import pytest


@pytest.mark.parametrize("offline", [True, False])
def test_workflow_failure_explains_connection_or_missing_bridge(client, monkeypatch, offline):
    async def unavailable(settings):
        request = httpx.Request("GET", "http://comfy.test/shotmill/v1/workflows")
        if offline:
            raise httpx.ConnectError("refused", request=request)
        response = httpx.Response(404, request=request)
        response.raise_for_status()

    monkeypatch.setattr("shotmill.api.comfyui.fetch_bridge_workflows", unavailable)
    result = client.get("/api/v1/comfyui/workflows")
    assert result.status_code == 503
    error = result.json()["error"]
    if offline:
        assert error["code"] == "COMFYUI_UNREACHABLE"
        assert "确认已启动" in error["message"]
    else:
        assert "未找到 Bridge" in error["message"]
        assert "确认已启动" not in error["message"]
