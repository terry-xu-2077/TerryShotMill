from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from shotmill.domain.application_settings import ComfyUISettings


def _workflow_root(settings: ComfyUISettings) -> Path | None:
    if not settings.root_path.strip():
        return None
    return Path(settings.root_path).expanduser() / settings.workflow_directory


def _bridge_port(node: dict[str, Any], direction: str) -> dict[str, str] | None:
    class_type = str(node.get("class_type") or node.get("type") or "")
    if class_type in {"ShotMillIOBridgeIn", "ShotMill.IOBridgeIn"} and direction == "input":
        return {"name": "*", "direction": "input", "type": "*"}
    if class_type in {"ShotMillIOBridgeOut", "ShotMill.IOBridgeOut"} and direction == "output":
        return {"name": "*", "direction": "output", "type": "*"}
    return None


def _read_workflow(path: Path, relative_path: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "id": relative_path,
            "name": path.stem,
            "file_name": path.name,
            "relative_path": relative_path,
            "format": "invalid",
            "executable": False,
            "has_shotmill_bridge": False,
            "inputs": [],
            "outputs": [],
            "warnings": [f"无法读取工作流：{exc}"],
        }

    nodes: list[dict[str, Any]] = []
    workflow_format = "canvas"
    prompt = raw.get("prompt") if isinstance(raw, dict) else None
    if isinstance(prompt, dict) and all(
        isinstance(item, dict) and item.get("class_type")
        for item in prompt.values()
    ):
        workflow_format = "api"
        nodes = list(prompt.values())
    elif isinstance(raw, dict) and isinstance(raw.get("nodes"), list):
        nodes = [item for item in raw["nodes"] if isinstance(item, dict)]
    elif isinstance(raw, dict) and all(
        isinstance(item, dict) and item.get("class_type") for item in raw.values()
    ):
        workflow_format = "api"
        nodes = list(raw.values())

    inputs = [port for node in nodes if (port := _bridge_port(node, "input"))]
    outputs = [port for node in nodes if (port := _bridge_port(node, "output"))]
    has_bridge = bool(inputs or outputs)
    if not has_bridge:
        return None
    warnings: list[str] = []
    executable = True

    return {
        "id": relative_path,
        "name": str((raw.get("extra") or {}).get("workflow_name") or path.stem)
        if isinstance(raw, dict)
        else path.stem,
        "file_name": path.name,
        "relative_path": relative_path,
        "format": workflow_format,
        "executable": executable,
        "has_shotmill_bridge": has_bridge,
        "inputs": inputs,
        "outputs": outputs,
        "warnings": warnings,
    }


def list_workflows(settings: ComfyUISettings) -> list[dict[str, Any]]:
    root = _workflow_root(settings)
    if root is None or not root.exists():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json"), key=lambda item: str(item).lower()):
        relative_path = path.relative_to(root).as_posix()
        item = _read_workflow(path, relative_path)
        if item is not None:
            result.append(item)
    return result


async def fetch_bridge_workflows(settings: ComfyUISettings) -> list[dict[str, Any]]:
    base_url = settings.base_url.rstrip("/")
    if not base_url:
        raise RuntimeError("ComfyUI 地址未配置")
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{base_url}/shotmill/v1/workflows")
        response.raise_for_status()
        payload = response.json()
    workflows = payload.get("workflows") if isinstance(payload, dict) else None
    if not isinstance(workflows, list):
        raise RuntimeError("ShotMill Bridge 返回的工作流目录格式无效")
    return [item for item in workflows if isinstance(item, dict)]
