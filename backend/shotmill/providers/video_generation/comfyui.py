from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from shotmill.domain.application_settings import WorkflowNumericBinding
from shotmill.domain.providers import (
    GeneratedOutput,
    VideoGenerationCapability,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from shotmill.errors import ProviderUnavailableError, ShotMillError
from shotmill.providers.comfyui_runtime import ComfyUIExecutionCoordinator
from shotmill.providers.video_generation.numeric_bindings import resolve_numeric_bindings
from shotmill.providers.video_generation.workflow_snapshot import checked_workflow_snapshot

_OPTIONAL_ASSET_PATTERN = re.compile(r"^\{\{asset\?:(.+)}}$")


def _bridge_payload(request, workflow_id, snapshot, input_slots, numeric_inputs):
    return {
        "jobId": request.job_id,
        "workflowId": workflow_id,
        "workflowSnapshot": snapshot,
        "finalPrompt": _context_prompt(request),
        "seed": request.seed if request.seed is not None else 0,
        "params": request.params,
        "inputSlots": input_slots,
        "numericInputs": numeric_inputs,
        "assets": [
            {"reference": media.reference, "mediaType": media.media_type}
            for media in request.assets
        ],
    }


def _preflight_message(response: httpx.Response) -> str:
    labels = {
        "required_input_missing": "缺少必填输入",
        "return_type_mismatch": "输入连接类型不匹配",
        "value_not_in_list": "所选模型或选项不可用",
        "value_smaller_than_min": "数值低于允许范围",
        "value_bigger_than_max": "数值超过允许范围",
        "dependency_cycle": "输入连接存在循环",
        "invalid_input_type": "输入值类型不正确",
        "custom_validation_failed": "输入未通过节点检查",
    }
    try:
        body = response.json()
        messages = []
        for node_id, node in body.get("nodeErrors", {}).items():
            for reason in node.get("errors", []):
                label = labels.get(reason.get("type"), reason.get("message") or "输入无效")
                details = str(reason.get("details") or "")
                messages.append(f"节点 {node_id}：{label}" + (f"（{details}）" if details else ""))
        if messages:
            return "；".join(messages[:8])[:3000]
        error = body.get("error", "")
        if isinstance(error, dict):
            details = [str(error[key]) for key in ("message", "details") if error.get(key)]
            return "：".join(details)[:3000]
        return str(error)[:3000] or "请检查工作流配置。"
    except (ValueError, TypeError, AttributeError):
        return "生成服务返回了无法识别的检查结果，请检查 Bridge。"


def _context_prompt(request: VideoGenerationRequest) -> str:
    instructions = []
    for media in request.assets:
        if media.role == "context_last_frame":
            instructions.append(
                f"{media.reference} is the exact final frame of the preceding shot. "
                "Begin from this visual state and continue the action, "
                "preserving character, vehicle, lighting and screen direction."
            )
        elif media.role == "context_segment":
            instructions.append(
                f"{media.reference} is the ending segment of the preceding shot. "
                "Continue immediately after its final moment, preserving motion, character, "
                "vehicle, lighting and screen direction. Do not replay the reference segment."
            )
    if not instructions:
        return request.final_prompt
    note = "\n".join(instructions)
    marker = "detailed_description:\n"
    if marker in request.final_prompt:
        return request.final_prompt.replace(marker, marker + note + "\n", 1)
    return request.final_prompt + "\n" + note


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
    progress_callback = None

    def set_progress_callback(self, callback):
        self.progress_callback = callback

    id = "comfyui"
    capability = VideoGenerationCapability(
        job_resumption=True,
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
        numeric_bindings_getter: Any | None = None,
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
        self.numeric_bindings_getter = numeric_bindings_getter
        self.numeric_bindings: tuple[WorkflowNumericBinding, ...] = ()
        self.use_bridge_assets = use_bridge_assets
        self.frozen_workflow_id: str | None = None
        self.workflow_snapshot: dict[str, Any] | None = None

    def capture_profile(self, request: VideoGenerationRequest) -> dict[str, Any]:
        base_url = self.base_url_getter() if self.base_url_getter is not None else self.base_url
        if not base_url:
            raise ProviderUnavailableError("请先配置 ComfyUI 地址。")
        return {
            "version": 2,
            "providerId": self.id,
            "baseUrl": base_url.rstrip("/"),
            "workflowId": self._load_workflow_id(request),
            "pollIntervalSeconds": self.poll_interval_seconds,
            "timeoutSeconds": self.timeout_seconds,
            "useBridgeAssets": self.use_bridge_assets,
            "numericBindings": [asdict(binding) for binding in self._numeric_bindings(request)],
        }

    def bind_profile(self, profile: dict[str, Any]) -> ComfyUIVideoGenerationProvider:
        if profile.get("version") != 2 or not profile.get("workflowId"):
            raise ShotMillError(
                "VIDEO_PROFILE_SNAPSHOT_MISSING", "旧视频任务缺少执行配置，请重新提交生成。", 409
            )
        provider = ComfyUIVideoGenerationProvider(
            profile["baseUrl"],
            None,
            poll_interval_seconds=profile["pollIntervalSeconds"],
            timeout_seconds=profile["timeoutSeconds"],
            use_bridge_assets=profile["useBridgeAssets"],
            transport=self.transport,
            coordinator=self.coordinator,
        )
        provider.frozen_workflow_id = profile["workflowId"]
        if profile.get("workflowSnapshot") is not None:
            provider.workflow_snapshot = checked_workflow_snapshot(
                profile["workflowSnapshot"],
                profile["workflowId"],
            )
        provider.numeric_bindings = tuple(
            WorkflowNumericBinding(**binding) for binding in profile.get("numericBindings", [])
        )
        return provider

    def _numeric_bindings(self, request: VideoGenerationRequest):
        return (
            self.numeric_bindings_getter(request)
            if self.numeric_bindings_getter
            else self.numeric_bindings
        )

    def _load_workflow_id(
        self,
        request: VideoGenerationRequest,
    ) -> str:
        if self.frozen_workflow_id is not None:
            return self.frozen_workflow_id
        workflow_template = self.workflow_template
        if self.workflow_path_getter is not None:
            workflow_template = self.workflow_path_getter(request) or workflow_template
        if workflow_template is None:
            raise ProviderUnavailableError(
                "ComfyUI workflow template is not configured. Set "
                "SHOTMILL_COMFYUI_WORKFLOW_TEMPLATE."
            )
        # The Bridge owns workflow lookup and capture. Local paths only supply
        # a stable relative filename; the backend never reads that local file.
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
        *,
        numeric_values: dict[str, float | int] | None = None,
        workflow_snapshot: dict[str, Any] | None = None,
    ) -> list[dict[str, str] | None]:
        snapshot = workflow_snapshot or self.workflow_snapshot
        if snapshot is not None:
            workflow = {"inputs": snapshot["inputs"], "executable": True}
        else:
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
                f"Bridge 中找不到工作流“{workflow_id}”，请重新选择工作流。",
                422,
            )
        if workflow.get("executable") is False:
            raise ShotMillError(
                "SHOTMILL_WORKFLOW_NOT_EXECUTABLE", "所选工作流无法执行，请检查工作流配置。", 422
            )
        ports = workflow.get("inputs") if isinstance(workflow.get("inputs"), list) else []
        values = resolve_numeric_bindings(
            self._numeric_bindings(request), ports, request.params.get("durationSeconds", 6)
        )
        if numeric_values is not None:
            numeric_values.update(values)
        media_ports = [
            port
            for port in ports
            if str(port.get("type") or "*").upper()
            not in {
                "STRING",
                "TEXT",
                "INT",
                "FLOAT",
                "BOOLEAN",
            }
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
        context = [
            media
            for media in request.assets
            if media.role in {"context_last_frame", "context_segment"}
        ]
        assets = [media for media in request.assets if media not in context]
        assigned = assets + [None] * (len(media_ports) - len(assets))
        if isinstance(selection, dict):
            if selection.get("workflowId") != workflow_id:
                raise ShotMillError(
                    "WORKFLOW_INPUTS_STALE", "输入槽位属于其他工作流，请重新选择资产", 422
                )
            slots = selection.get("slots", [])
            by_reference = {media.reference: media for media in assets}
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
        for media in context:
            actual = media_types[media.media_type]
            index = next(
                (
                    i
                    for i, port in enumerate(media_ports)
                    if assigned[i] is None and str(port.get("type") or "*").upper() in {"*", actual}
                ),
                None,
            )
            if index is None:
                raise ShotMillError(
                    "CONTEXT_INPUT_UNAVAILABLE",
                    f"工作流没有空闲的 {actual} 入口用于承接，请配置对应输入。",
                    422,
                )
            assigned[index] = media
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

    async def validate(self, request: VideoGenerationRequest) -> dict[str, Any]:
        base_url = self.base_url_getter() if self.base_url_getter is not None else self.base_url
        if not base_url:
            raise ProviderUnavailableError("请先配置 ComfyUI 地址。")
        try:
            async with httpx.AsyncClient(timeout=5.0, transport=self.transport) as client:
                workflow_id = self._load_workflow_id(request)
                await self._validate_workflow_inputs(
                    client, base_url.rstrip("/"), workflow_id, request
                )
                snapshot = self.workflow_snapshot
                if snapshot is None:
                    response = await client.get(
                        f"{base_url.rstrip('/')}/shotmill/v1/workflows/snapshot",
                        params={"workflowId": workflow_id},
                    )
                    if response.status_code == 404:
                        raise ShotMillError(
                            "WORKFLOW_SNAPSHOT_UNAVAILABLE",
                            "无法取得工作流快照，请确认文件仍存在并将 Bridge 更新到 0.3.0。",
                            422,
                        )
                    if response.is_client_error:
                        raise ShotMillError(
                            "WORKFLOW_COMPILE_FAILED",
                            f"工作流编译失败：{response.text[:12000]}",
                            422,
                        )
                    response.raise_for_status()
                    captured = response.json()
                    if not isinstance(captured, dict):
                        raise ValueError("snapshot response must be an object")
                    snapshot = checked_workflow_snapshot(
                        captured.get("snapshot"),
                        workflow_id,
                    )
                # A file can change between catalogue lookup and capture. Only
                # the ports captured with the execution graph govern the Job.
                numeric_inputs: dict[str, float | int] = {}
                input_slots = await self._validate_workflow_inputs(
                    client,
                    base_url.rstrip("/"),
                    workflow_id,
                    request,
                    workflow_snapshot=snapshot,
                    numeric_values=numeric_inputs,
                )
                preflight = await client.post(
                    f"{base_url.rstrip('/')}/shotmill/v1/workflows/validate",
                    json=_bridge_payload(
                        request,
                        workflow_id,
                        snapshot,
                        input_slots,
                        numeric_inputs,
                    ),
                    timeout=30.0,
                )
                if preflight.status_code == 404:
                    raise ShotMillError(
                        "WORKFLOW_PREFLIGHT_UNAVAILABLE",
                        "请将 Bridge 更新到 0.3.1 以检查工作流。",
                        422,
                    )
                if preflight.is_client_error:
                    raise ShotMillError(
                        "WORKFLOW_PREFLIGHT_FAILED",
                        f"工作流生成前检查失败：{_preflight_message(preflight)}",
                        422,
                    )
                preflight.raise_for_status()
                validation = preflight.json()
                if not isinstance(validation, dict) or validation.get("ok") is not True:
                    raise ValueError("invalid preflight response")
                return {"workflowSnapshot": snapshot}
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("无法检查 ComfyUI 工作流，请确认服务连接。") from exc
        except (ValueError, TypeError) as exc:
            raise ShotMillError(
                "SHOTMILL_BRIDGE_INVALID_RESPONSE", "工作流目录响应无效，请检查 Bridge。", 502
            ) from exc

    async def _collect_bridge_job(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        job_id: str,
        prompt_id: str | None = None,
    ) -> VideoGenerationResponse:
        from .progress import StepProgress, watch_progress

        monitor = None
        if self.progress_callback and prompt_id:
            graph = (self.workflow_snapshot or {}).get("prompt", {})
            monitor = asyncio.create_task(
                watch_progress(
                    base_url,
                    f"shotmill-{job_id}",
                    StepProgress(prompt_id, graph),
                    self.progress_callback,
                )
            )
        try:
            return await self._poll_bridge_job(client, base_url, job_id, prompt_id)
        finally:
            if monitor:
                monitor.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor

    async def _poll_bridge_job(self, client, base_url, job_id, prompt_id):
        started = time.monotonic()
        while time.monotonic() - started < self.timeout_seconds:
            response = await client.get(f"{base_url}/shotmill/v1/jobs/{job_id}")
            if response.status_code == 404:
                raise ShotMillError(
                    "SHOTMILL_BRIDGE_JOB_NOT_FOUND",
                    "生成服务找不到原视频任务，请检查运行记录。",
                    502,
                )
            response.raise_for_status()
            try:
                state = response.json()
            except ValueError as exc:
                raise ShotMillError(
                    "SHOTMILL_BRIDGE_INVALID_RESPONSE",
                    "生成服务返回了无效任务状态。",
                    502,
                ) from exc
            if not isinstance(state, dict):
                raise ShotMillError(
                    "SHOTMILL_BRIDGE_INVALID_RESPONSE",
                    "生成服务返回了无效任务状态。",
                    502,
                )
            if state.get("status") == "not_found":
                raise ShotMillError(
                    "SHOTMILL_BRIDGE_JOB_NOT_FOUND",
                    "生成服务找不到原视频任务，请检查运行记录。",
                    502,
                )
            if state.get("status") == "failed":
                raise ShotMillError(
                    "SHOTMILL_BRIDGE_JOB_FAILED",
                    str(state.get("error") or "Bridge job failed"),
                    502,
                )
            if state.get("status") == "completed":
                outputs = await self._fetch_bridge_outputs(
                    client,
                    base_url,
                    job_id,
                    state.get("results", []),
                )
                if not outputs:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_NO_OUTPUT",
                        "ShotMill IO Bridge completed without downloadable outputs",
                        502,
                    )
                remote_id = state.get("promptId") or state.get("prompt_id") or prompt_id
                if not remote_id:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_INVALID_RESPONSE",
                        "原视频任务缺少生成记录标识。",
                        502,
                    )
                return VideoGenerationResponse(str(remote_id), tuple(outputs))
            await asyncio.sleep(self.poll_interval_seconds)
        raise ShotMillError(
            "SHOTMILL_BRIDGE_TIMEOUT",
            "Timed out waiting for ShotMill IO Bridge generation",
            504,
        )

    async def stop(self, job_id: str) -> None:
        base = self.base_url_getter() if self.base_url_getter else self.base_url
        async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
            response = await client.get(f"{base}/shotmill/v1/jobs/{job_id}")
            response.raise_for_status()
            state = response.json()
            remote = state.get("promptId") or state.get("prompt_id")
            if state.get("status") in {"completed", "failed"}:
                return
            if not remote:
                raise ShotMillError("STOP_NOT_READY", "任务尚在准备，请稍后重试停止。", 409)
            # Both calls target the exact remote prompt; never interrupt unrelated work.
            deleted = await client.post(f"{base}/queue", json={"delete": [remote]})
            deleted.raise_for_status()
            interrupted = await client.post(f"{base}/interrupt", json={"prompt_id": remote})
            interrupted.raise_for_status()

    async def resume(self, job_id: str) -> VideoGenerationResponse:
        # Only observe the persisted logical job and download its original outputs.
        # No upload, workflow validation, model unloading or resubmission is allowed here.
        base_url = self.base_url_getter() if self.base_url_getter is not None else self.base_url
        if not base_url:
            raise ProviderUnavailableError("请先配置 ComfyUI 地址。")
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=self.transport) as client:
                return await self._collect_bridge_job(client, base_url.rstrip("/"), job_id)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"ComfyUI request failed: {exc}") from exc

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        if self.frozen_workflow_id is None:
            profile = self.capture_profile(request)
            profile.update(await self.bind_profile(profile).validate(request))
            return await self.bind_profile(profile).generate(request)
        if self.workflow_snapshot is None:
            raise ShotMillError(
                "WORKFLOW_SNAPSHOT_MISSING",
                "视频任务缺少工作流内容快照，请重新提交生成。",
                409,
            )
        base_url = self.base_url_getter() if self.base_url_getter is not None else self.base_url
        base_url = base_url.rstrip("/") if base_url else None
        if not base_url:
            raise ProviderUnavailableError(
                "ComfyUI endpoint is not configured. Set SHOTMILL_COMFYUI_BASE_URL "
                "or SHOTMILL_COMFYUI_ENDPOINT."
            )
        client_id = f"shotmill-{request.job_id}"
        coordinator_acquired = False
        try:
            async with httpx.AsyncClient(
                timeout=60.0,
                transport=self.transport,
            ) as client:
                workflow_id = self._load_workflow_id(request)
                numeric_inputs: dict[str, float | int] = {}
                input_slots = await self._validate_workflow_inputs(
                    client,
                    base_url,
                    workflow_id,
                    request,
                    numeric_values=numeric_inputs,
                )
                if self.coordinator is not None:
                    await self.coordinator.prepare("video", client, base_url)
                    coordinator_acquired = True
                asset_values = await self._upload_assets(client, request, base_url)
                submit = await client.post(
                    f"{base_url}/shotmill/v1/jobs",
                    json={
                        **_bridge_payload(
                            request,
                            workflow_id,
                            self.workflow_snapshot,
                            input_slots,
                            numeric_inputs,
                        ),
                        "clientId": client_id,
                        "assetValues": asset_values,
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

                return await self._collect_bridge_job(
                    client,
                    base_url,
                    request.job_id,
                    str(prompt_id),
                )
        except ShotMillError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"ComfyUI request failed: {exc}") from exc
        finally:
            if coordinator_acquired and self.coordinator is not None:
                await self.coordinator.finish()
