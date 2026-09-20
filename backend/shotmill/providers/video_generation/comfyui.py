from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from shotmill.domain.providers import (
    GeneratedOutput,
    VideoGenerationCapability,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from shotmill.errors import ProviderUnavailableError, ShotMillError
from shotmill.providers.comfyui_runtime import ComfyUIExecutionCoordinator

_OPTIONAL_ASSET_PATTERN = re.compile(r"^\{\{asset\?:(.+)}}$")


def _asset_value(
    reference: str,
    request: VideoGenerationRequest,
    asset_values: dict[str, str] | None,
) -> str:
    if asset_values is not None and reference in asset_values:
        return asset_values[reference]
    assets = {item.reference: item for item in request.assets}
    media = assets.get(reference)
    if media is None:
        raise ShotMillError(
            "GENERATION_ASSET_REFERENCE_NOT_FOUND",
            f"Workflow requires missing asset reference: {reference}",
            422,
        )
    return str(media.path)


def _replace_placeholders(
    value: Any,
    request: VideoGenerationRequest,
    asset_values: dict[str, str] | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_placeholders(item, request, asset_values) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_placeholders(item, request, asset_values) for item in value]
    if not isinstance(value, str):
        return value

    if value == "{{final_prompt}}":
        return request.final_prompt
    if value == "{{seed}}":
        return request.seed if request.seed is not None else 0
    if value == "{{job_id}}":
        return request.job_id
    if value.startswith("{{asset:") and value.endswith("}}"):
        reference = value[len("{{asset:") : -2]
        return _asset_value(reference, request, asset_values)
    optional_match = _OPTIONAL_ASSET_PATTERN.fullmatch(value)
    if optional_match:
        return _asset_value(optional_match.group(1), request, asset_values)
    if value.startswith("{{param:") and value.endswith("}}"):
        key = value[len("{{param:") : -2]
        return request.params.get(key)

    replaced = value.replace("{{final_prompt}}", request.final_prompt)
    replaced = replaced.replace("{{job_id}}", request.job_id)
    if request.seed is not None:
        replaced = replaced.replace("{{seed}}", str(request.seed))
    for media in request.assets:
        replacement = _asset_value(media.reference, request, asset_values)
        replaced = replaced.replace(f"{{{{asset:{media.reference}}}}}", replacement)
        replaced = replaced.replace(f"{{{{asset?:{media.reference}}}}}", replacement)
    for key, item in request.params.items():
        replaced = replaced.replace(f"{{{{param:{key}}}}}", str(item))
    return replaced


def _contains_missing_optional_asset(value: Any, references: set[str]) -> bool:
    if isinstance(value, dict):
        return any(_contains_missing_optional_asset(item, references) for item in value.values())
    if isinstance(value, list):
        return any(_contains_missing_optional_asset(item, references) for item in value)
    if not isinstance(value, str):
        return False
    match = _OPTIONAL_ASSET_PATTERN.fullmatch(value)
    return match is not None and match.group(1) not in references


def _prune_missing_optional_assets(
    workflow: dict[str, Any], request: VideoGenerationRequest
) -> dict[str, Any]:
    references = {item.reference for item in request.assets}
    removed = {
        str(node_id)
        for node_id, node in workflow.items()
        if _contains_missing_optional_asset(node, references)
    }
    if not removed:
        return workflow

    kept = {str(node_id): node for node_id, node in workflow.items() if str(node_id) not in removed}
    for node in kept.values():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        node["inputs"] = {
            name: value
            for name, value in node["inputs"].items()
            if not (isinstance(value, list) and len(value) == 2 and str(value[0]) in removed)
        }
    return kept


class ComfyUIVideoGenerationProvider:
    id = "comfyui"
    capability = VideoGenerationCapability(
        text=True,
        image=True,
        first_frame=True,
        last_frame=True,
        reference_images=True,
        reference_videos=True,
        max_duration_seconds=None,
        continuation=True,
        progress_reporting=True,
        batch=False,
        max_concurrency=1,
    )

    def __init__(
        self,
        base_url: str | None,
        workflow_template: Path | None,
        *,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
        coordinator: ComfyUIExecutionCoordinator | None = None,
        base_url_getter: Any | None = None,
        workflow_path_getter: Any | None = None,
        use_bridge_assets: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.workflow_template = workflow_template
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.coordinator = coordinator
        self.base_url_getter = base_url_getter
        self.workflow_path_getter = workflow_path_getter
        self.use_bridge_assets = use_bridge_assets

    def _load_workflow_id(
        self,
        request: VideoGenerationRequest,
    ) -> str:
        workflow_template = self.workflow_template
        if self.workflow_path_getter is not None:
            workflow_template = self.workflow_path_getter(request) or workflow_template
        if workflow_template is None:
            raise ProviderUnavailableError(
                "ComfyUI workflow template is not configured. Set "
                "SHOTMILL_COMFYUI_WORKFLOW_TEMPLATE."
            )
        # Only the Bridge knows the ComfyUI workflow directory. Send its stable
        # filename rather than reading or forwarding the workflow JSON here.
        parts = workflow_template.parts
        workflow_index = next(
            (index for index, part in enumerate(parts) if part.lower() == "workflows"),
            None,
        )
        if workflow_index is not None and workflow_index + 1 < len(parts):
            return Path(*parts[workflow_index + 1 :]).as_posix()
        return workflow_template.name

    async def _validate_workflow_inputs(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        workflow_id: str,
        request: VideoGenerationRequest,
    ) -> list[dict[str, str] | None]:
        response = await client.get(f"{base_url}/shotmill/v1/workflows")
        response.raise_for_status()
        payload = response.json()
        workflows = payload.get("workflows") if isinstance(payload, dict) else None
        workflow = next(
            (
                item
                for item in workflows or []
                if isinstance(item, dict)
                and str(item.get("relativePath") or item.get("id") or "") == workflow_id
            ),
            None,
        )
        if workflow is None:
            raise ShotMillError(
                "SHOTMILL_WORKFLOW_NOT_REGISTERED",
                f"Workflow is not exposed by ShotMill IO Bridge: {workflow_id}",
                422,
            )
        ports = workflow.get("inputs") if isinstance(workflow.get("inputs"), list) else []
        media_ports = [
            port for port in ports if str(port.get("type") or "*").upper() not in {"STRING", "TEXT"}
        ]
        if len(request.assets) > len(media_ports):
            raise ShotMillError(
                "SHOTMILL_WORKFLOW_INPUTS_INSUFFICIENT",
                f"任务有 {len(request.assets)} 个输入资产，但工作流声明了 "
                f"{len(media_ports)} 个媒体输入端口",
                422,
            )
        media_types = {
            "image": "IMAGE",
            "video": "VIDEO",
            "audio": "AUDIO",
        }
        selection = request.params.get("workflowInputs")
        assigned = list(request.assets) + [None] * (len(media_ports) - len(request.assets))
        if isinstance(selection, dict):
            if selection.get("workflowId") != workflow_id:
                raise ShotMillError(
                    "WORKFLOW_INPUTS_STALE", "输入槽位属于其他工作流，请重新选择资产", 422
                )
            slots = selection.get("slots", [])
            by_reference = {media.reference: media for media in request.assets}
            port_ids = [
                f"{port.get('targetNodeId', '')}:"
                f"{port.get('targetPort') or port.get('portName') or port.get('name', '')}:"
                f"{port.get('sourceNodeId', '')}"
                for port in media_ports
            ]
            assigned = [None] * len(media_ports)
            seen = set()
            for slot in slots:
                if not slot.get("assetId"):
                    continue
                port_id = slot.get("portId")
                media = by_reference.get(slot.get("reference"))
                if (
                    port_id not in port_ids
                    or port_id in seen
                    or media is None
                    or media.asset_id != slot["assetId"]
                ):
                    raise ShotMillError(
                        "WORKFLOW_INPUTS_STALE", "输入槽位或资产已变化，请重新确认槽位", 422
                    )
                seen.add(port_id)
                assigned[port_ids.index(port_id)] = media
            if {media.reference for media in assigned if media} != set(by_reference):
                raise ShotMillError("WORKFLOW_INPUTS_UNASSIGNED", "存在未分配到槽位的资产", 422)
        for index, (media, port) in enumerate(zip(assigned, media_ports, strict=True), start=1):
            if media is None:
                continue
            expected = str(port.get("type") or "*").upper()
            actual = media_types.get(media.media_type, media.media_type.upper())
            if expected not in {"", "*", actual}:
                raise ShotMillError(
                    "SHOTMILL_WORKFLOW_INPUT_TYPE_MISMATCH",
                    f"第 {index} 个输入端口要求 {expected}，任务提供的是 {actual}",
                    422,
                )
        return [
            {"reference": media.reference, "mediaType": media.media_type} if media else None
            for media in assigned
        ]

    async def _upload_assets(
        self,
        client: httpx.AsyncClient,
        request: VideoGenerationRequest,
        base_url: str,
    ) -> dict[str, str]:
        uploaded: dict[str, str] = {}
        for media in request.assets:
            safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", media.asset_id).strip("._")
            filename = f"{safe_id or 'asset'}{media.path.suffix.lower()}"
            content = media.path.read_bytes()
            response = await client.post(
                f"{base_url}/shotmill/v1/assets",
                data={"asset_id": media.asset_id, "role": media.role or ""},
                files={
                    "file": (
                        filename,
                        content,
                        media.mime_type or "application/octet-stream",
                    )
                },
            )
            response.raise_for_status()
            payload = response.json()
            bridge_asset = payload.get("asset") if isinstance(payload, dict) else None
            remote_name = (
                bridge_asset.get("relativePath")
                if isinstance(bridge_asset, dict)
                else payload.get("name")
                if isinstance(payload, dict)
                else None
            )
            if not remote_name:
                raise ShotMillError(
                    "COMFYUI_INVALID_UPLOAD_RESPONSE",
                    "ComfyUI did not return an uploaded asset filename",
                    502,
                )
            uploaded[media.reference] = str(remote_name)
        return uploaded

    async def _fetch_bridge_outputs(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        job_id: str,
        items: list[dict[str, Any]],
    ) -> list[GeneratedOutput]:
        outputs: list[GeneratedOutput] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("filename"):
                continue
            media_response = await client.get(
                f"{base_url}/shotmill/v1/results/{job_id}/files/{index}"
            )
            media_response.raise_for_status()
            outputs.append(
                GeneratedOutput(
                    filename=str(item["filename"]),
                    content=media_response.content,
                    content_type=media_response.headers.get("content-type"),
                    metadata={
                        "source": "shotmill_bridge",
                        "jobId": job_id,
                        "relativePath": item.get("relativePath", ""),
                        "nodeId": item.get("nodeId", ""),
                    },
                )
            )
        return outputs

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        base_url = self.base_url_getter() if self.base_url_getter is not None else self.base_url
        base_url = base_url.rstrip("/") if base_url else None
        if not base_url:
            raise ProviderUnavailableError(
                "ComfyUI endpoint is not configured. Set SHOTMILL_COMFYUI_BASE_URL "
                "or SHOTMILL_COMFYUI_ENDPOINT."
            )
        client_id = f"shotmill-{uuid4().hex}"
        coordinator_acquired = False
        try:
            async with httpx.AsyncClient(
                timeout=60.0,
                transport=self.transport,
            ) as client:
                workflow_id = self._load_workflow_id(request)
                input_slots = await self._validate_workflow_inputs(
                    client, base_url, workflow_id, request
                )
                if self.coordinator is not None:
                    await self.coordinator.prepare("video", client, base_url)
                    coordinator_acquired = True
                asset_values = await self._upload_assets(client, request, base_url)
                submit = await client.post(
                    f"{base_url}/shotmill/v1/jobs",
                    json={
                        "jobId": request.job_id,
                        "workflowId": workflow_id,
                        "clientId": client_id,
                        "finalPrompt": request.final_prompt,
                        "seed": request.seed if request.seed is not None else 0,
                        "params": request.params,
                        "assetValues": asset_values,
                        "inputSlots": input_slots,
                        "assets": [
                            {
                                "reference": media.reference,
                                "mediaType": media.media_type,
                            }
                            for media in request.assets
                        ],
                    },
                )
                if submit.is_client_error:
                    try:
                        details = json.dumps(submit.json(), ensure_ascii=False)
                    except ValueError:
                        details = submit.text
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_SUBMISSION_REJECTED",
                        f"Bridge 拒绝生成请求（{submit.status_code}）：{details[:12000]}",
                        422,
                    )
                submit.raise_for_status()
                submitted = submit.json()
                prompt_id = submitted.get("promptId") or submitted.get("prompt_id")
                if not prompt_id:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_INVALID_RESPONSE",
                        "ShotMill IO Bridge did not return promptId",
                        502,
                    )

                started = time.monotonic()
                bridge_state: dict[str, Any] | None = None
                while time.monotonic() - started < self.timeout_seconds:
                    state_response = await client.get(
                        f"{base_url}/shotmill/v1/jobs/{request.job_id}"
                    )
                    if state_response.status_code == 404:
                        raise ShotMillError(
                            "SHOTMILL_BRIDGE_JOB_NOT_FOUND",
                            "ShotMill IO Bridge lost the submitted job",
                            502,
                        )
                    state_response.raise_for_status()
                    state = state_response.json()
                    if state.get("status") == "failed":
                        raise ShotMillError(
                            "SHOTMILL_BRIDGE_JOB_FAILED",
                            str(state.get("error") or "Bridge job failed"),
                            502,
                        )
                    if state.get("status") == "completed":
                        bridge_state = state
                        break
                    await asyncio.sleep(self.poll_interval_seconds)
                if bridge_state is None:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_TIMEOUT",
                        "Timed out waiting for ShotMill IO Bridge generation",
                        504,
                    )

                outputs = await self._fetch_bridge_outputs(
                    client,
                    base_url,
                    request.job_id,
                    bridge_state.get("results", []),
                )
                if not outputs:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_NO_OUTPUT",
                        "ShotMill IO Bridge completed without downloadable outputs",
                        502,
                    )
                return VideoGenerationResponse(
                    provider_job_id=str(prompt_id),
                    outputs=tuple(outputs),
                )
        except ShotMillError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"ComfyUI request failed: {exc}") from exc
        finally:
            if coordinator_acquired and self.coordinator is not None:
                await self.coordinator.finish()
