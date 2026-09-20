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
    except (httpx.HTTPError, RuntimeError) as exc:
        raise ShotMillError(
            "WORKFLOW_CATALOG_UNAVAILABLE",
            "暂时无法读取工作流输入槽位，请确认 Bridge 已连接后重试。",
            503,
        ) from exc


@router.get("/status", response_model=ComfyUIStatusView)
async def get_status(container: ContainerDep) -> ComfyUIStatusView:
    settings = container.application_settings.get_comfyui()
    base_url = settings.base_url.rstrip("/")
    try:
        workflows = await _workflow_views(container)
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
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            system = await client.get(f"{base_url}/system_stats")
            system.raise_for_status()
            bridge = await client.get(f"{base_url}/shotmill/v1/health")
            return ComfyUIStatusView(
                connected=True,
                base_url=base_url,
                bridge_node_available=bridge.status_code == 200,
                message=(
                    "ComfyUI 已连接。"
                    if bridge.status_code == 200
                    else "ComfyUI 已连接，但未发现 ComfyUI-ShotMill Bridge。"
                ),
                workflows=workflows,
            )
    except (httpx.HTTPError, OSError) as exc:
        return ComfyUIStatusView(
            connected=False,
            base_url=base_url,
            bridge_node_available=False,
            message=f"无法连接 ComfyUI：{exc}",
            workflows=workflows,
        )
