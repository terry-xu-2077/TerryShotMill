from __future__ import annotations

import httpx
from fastapi import APIRouter

from shotmill.api.dependencies import ContainerDep
from shotmill.errors import ShotMillError
from shotmill.frontend_adapter.models import (
    ComfyUIStatusView,
    ComfyUIWorkflowView,
)
from shotmill.providers.comfyui_workflows import fetch_bridge_workflows

router = APIRouter(prefix="/comfyui", tags=["comfyui"])


async def _workflow_views(container: ContainerDep) -> list[ComfyUIWorkflowView]:
    items = await fetch_bridge_workflows(container.application_settings.get_comfyui())
    return [ComfyUIWorkflowView(**item) for item in items]


@router.get("/workflows", response_model=list[ComfyUIWorkflowView])
async def get_workflows(container: ContainerDep) -> list[ComfyUIWorkflowView]:
    try:
        return await _workflow_views(container)
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ShotMillError(
            "COMFYUI_UNREACHABLE",
            "无法连接 ComfyUI，请确认已启动且地址正确；连接后重试读取槽位。",
            503,
        ) from exc
    except httpx.HTTPStatusError as exc:
        message = (
            "ComfyUI 已响应，但未找到 Bridge；请启用 ShotMill Bridge 后重试读取槽位。"
            if exc.response.status_code == 404
            else "ComfyUI Bridge 返回异常，暂时无法读取槽位，请检查服务后重试。"
        )
        raise ShotMillError("WORKFLOW_CATALOG_UNAVAILABLE", message, 503) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        raise ShotMillError(
            "WORKFLOW_CATALOG_UNAVAILABLE",
            "暂时无法读取工作流输入槽位，请确认 Bridge 已连接后重试。",
            503,
        ) from exc


@router.get("/status", response_model=ComfyUIStatusView)
async def get_status(container: ContainerDep, include_workflows: bool = False) -> ComfyUIStatusView:
    settings = container.application_settings.get_comfyui()
    base_url = settings.base_url.rstrip("/")
    try:
        workflows = await _workflow_views(container) if include_workflows else []
    except (httpx.HTTPError, RuntimeError):
        workflows = []
    if not base_url:
        return ComfyUIStatusView(
            connected=False,
            base_url="",
            bridge_node_available=False,
            message="尚未配置 ComfyUI 地址。",
            workflows=workflows,
        )
    connected = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            system = await client.get(f"{base_url}/system_stats")
            system.raise_for_status()
            connected = True
            bridge = await client.get(f"{base_url}/shotmill/v1/health")
            healthy = False
            if bridge.status_code == 200:
                payload = bridge.json()
                healthy = isinstance(payload, dict) and payload.get("ok") is True
            state = "connected" if healthy else "missing" if bridge.status_code == 404 else "error"
            return ComfyUIStatusView(
                connected=True,
                base_url=base_url,
                bridge_node_available=healthy,
                bridge_state=state,
                message=(
                    "ComfyUI Bridge 已连接。" if healthy
                    else "ComfyUI 已连接，但未发现 ComfyUI-ShotMill Bridge。" if state == "missing"
                    else "ComfyUI 已连接，但 Bridge 通信异常，请检查 Bridge 后重试。"
                ),
                workflows=workflows,
            )
    except (httpx.HTTPError, OSError, ValueError):
        return ComfyUIStatusView(
            connected=connected,
            base_url=base_url,
            bridge_node_available=False,
            bridge_state="error" if connected else "disconnected",
            message=("ComfyUI 已连接，但 Bridge 未正常响应，请重试。" if connected
                     else "无法连接 ComfyUI，请检查地址及服务状态。"),
            workflows=workflows,
        )
