from __future__ import annotations

import asyncio
import mimetypes
import secrets
import time
from copy import deepcopy
from dataclasses import asdict, replace
from typing import Any
from uuid import uuid4

import httpx

from shotmill.domain.application_settings import LocalInferenceSettings
from shotmill.domain.providers import (
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
)
from shotmill.errors import ProviderUnavailableError, ShotMillError
from shotmill.providers.comfyui_runtime import ComfyUIExecutionCoordinator

# Defaults copied from the reference H3 prompt workflow. The workflow itself
# is not a runtime dependency: ShotMill builds the API graph below.
LLAMA_CPP_VLLM_DEFAULTS: dict[str, Any] = {
    "model": "Qwen3.8-27B-Q4_K_M.gguf",
    "mmproj": "Qwen3.8-27B-mmproj-BF16.gguf",
    "chat_handler": "Qwen3.8-Thinking",
    "n_ctx": 16384,
    "vram_limit": -1,
    "image_min_tokens": 0,
    "image_max_tokens": 0,
    "load_mtp": False,
    "preset_prompt": "Empty - Nothing",
    "inference_mode": "images",
    "max_frames": 24,
    "max_size": 256,
    "force_offload": False,
    "save_states": False,
}

def _extract_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        for item in value:
            result = _extract_text(item)
            if result:
                return result
    if isinstance(value, dict):
        for key in ("string", "text", "output", "value"):
            result = _extract_text(value.get(key))
            if result:
                return result
    return None


def _clean_model_text(value: str) -> str:
    """Handle both normal and llama outputs with a missing <think> opener."""
    cleaned = value.strip()
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[-1].strip()
    return cleaned


def _raise_for_comfyui(response: httpx.Response, operation: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text.strip().replace("\r", " ").replace("\n", " ")
        if len(detail) > 2000:
            detail = detail[:2000] + "..."
        raise ProviderUnavailableError(
            f"ComfyUI {operation} failed ({response.status_code}): {detail}"
        ) from exc


def _picture_slot(reference: str) -> int | None:
    prefix = "<Picture "
    if not reference.startswith(prefix) or not reference.endswith(">"):
        return None
    try:
        slot = int(reference[len(prefix) : -1])
    except ValueError:
        return None
    return slot if 1 <= slot <= 3 else None


def _build_workflow(
    request: PromptAIRequest,
    uploaded: dict[str, str],
    seed: int,
    settings: LocalInferenceSettings | None = None,
    model_inputs: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the API graph for ComfyUI-llama-cpp_vllm from adapter defaults."""

    settings = settings or LocalInferenceSettings()
    model_inputs = model_inputs or LLAMA_CPP_VLLM_DEFAULTS

    slot_media: dict[int, Any] = {}
    unassigned: list[Any] = []
    for media in request.media:
        slot = _picture_slot(media.reference)
        if slot is not None and slot not in slot_media:
            slot_media[slot] = media
        else:
            unassigned.append(media)
    for slot in range(1, 4):
        if slot not in slot_media and unassigned:
            slot_media[slot] = unassigned.pop(0)

    workflow: dict[str, dict[str, Any]] = {
        "3": {
            "inputs": {
                "model": model_inputs["model"],
                "mmproj": model_inputs["mmproj"],
                "chat_handler": model_inputs["chat_handler"],
                "n_ctx": model_inputs["n_ctx"],
                "vram_limit": model_inputs["vram_limit"],
                "image_min_tokens": model_inputs["image_min_tokens"],
                "image_max_tokens": model_inputs["image_max_tokens"],
                "load_mtp": model_inputs["load_mtp"],
            },
            "class_type": "llama_cpp_model_loader",
        },
        "1": {
            "inputs": {
                "llama_model": ["3", 0],
                "preset_prompt": settings.preset_prompt,
                "custom_prompt": request.user_text,
                "system_prompt": request.system_prompt,
                "inference_mode": settings.inference_mode,
                "max_frames": settings.max_frames,
                "max_size": settings.max_size,
                "seed": seed,
                "force_offload": settings.force_offload,
                "save_states": settings.save_states,
            },
            "class_type": "llama_cpp_instruct_adv",
        },
        # llama_cpp_instruct_adv returns strings but is not an OUTPUT_NODE.
        # This tiny sink makes ComfyUI execute the graph and keeps node 1's
        # first STRING output available in history.
        "15": {
            "inputs": {
                "prompt": "",
                "source_text": ["1", 0],
                "visual_preview": False,
                "edit_mode": False,
            },
            "class_type": "TerryXuH3PromptEditor",
        },
    }

    image_links: list[list[Any]] = []
    for slot in range(1, 4):
        media = slot_media.get(slot)
        if media is None:
            continue
        remote_name = uploaded.get(media.reference)
        if not remote_name:
            continue
        node_id = str(5 + slot)
        workflow[node_id] = {
            "inputs": {"image": remote_name},
            "class_type": "LoadImage",
        }
        image_link = [node_id, 0]
        image_links.append(image_link)

    if image_links:
        workflow["12"] = {
            "inputs": {
                f"inputs.input{index}": link
                for index, link in enumerate(image_links)
            },
            "class_type": "CreateList",
        }
        workflow["1"]["inputs"]["images"] = ["12", 0]

    return workflow


class ComfyUIPromptAIProvider:
    id = "comfyui-llama-cpp-vllm"
    capability = PromptAIProviderCapability(
        image_input=True,
        native_video_input=False,
        sampled_video_frames=False,
        audio_understanding=False,
        system_prompt=True,
        structured_output=False,
    )

    def __init__(
        self,
        base_url: str | None,
        *,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
        settings_getter: Any | None = None,
        system_prompt_getter: Any | None = None,
        base_url_getter: Any | None = None,
        use_bridge_assets: bool = False,
        coordinator: ComfyUIExecutionCoordinator | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.settings_getter = settings_getter
        self.system_prompt_getter = system_prompt_getter
        self.base_url_getter = base_url_getter
        self.use_bridge_assets = use_bridge_assets
        self.coordinator = coordinator
        self.model_inputs = dict(LLAMA_CPP_VLLM_DEFAULTS)

    @property
    def display_name(self) -> str:
        model = str(self.model_inputs["model"]).replace("\\", "/").rsplit("/", 1)[-1]
        return f"本地 · {model}"

    def capture_profile(self) -> dict[str, Any]:
        settings = self.settings_getter() if self.settings_getter else LocalInferenceSettings()
        if settings.seed_mode != "fixed":
            settings = replace(settings, seed_mode="fixed", seed=secrets.randbelow(2**63 - 1))
        return {
            "providerId": self.id, "version": 1,
            "baseUrl": self.base_url_getter() if self.base_url_getter else self.base_url,
            "localInference": asdict(settings), "modelInputs": deepcopy(self.model_inputs),
            "systemPrompt": (
                self.system_prompt_getter().system_prompt if self.system_prompt_getter else None
            ),
            "timeoutSeconds": self.timeout_seconds,
        }

    def bind_profile(self, profile: dict[str, Any]) -> ComfyUIPromptAIProvider:
        settings = LocalInferenceSettings(**profile["localInference"])
        provider = ComfyUIPromptAIProvider(
            profile["baseUrl"], poll_interval_seconds=self.poll_interval_seconds,
            timeout_seconds=profile["timeoutSeconds"], transport=self.transport,
            settings_getter=lambda: settings, use_bridge_assets=self.use_bridge_assets,
            coordinator=self.coordinator,
        )
        provider.model_inputs = deepcopy(profile["modelInputs"])
        # Bind the previously selected rules; do not consult settings after queue admission.
        if profile.get("systemPrompt") is not None:
            from shotmill.domain.application_settings import PromptSystemSettings
            frozen_system = PromptSystemSettings(system_prompt=profile["systemPrompt"])
            provider.system_prompt_getter = lambda: frozen_system
        return provider

    async def _upload_assets(
        self,
        client: httpx.AsyncClient,
        request: PromptAIRequest,
        base_url: str,
    ) -> dict[str, str]:
        uploaded: dict[str, str] = {}
        for media in request.media:
            if media.media_type != "image":
                raise ShotMillError(
                    "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                    "Local ComfyUI llama-cpp_vllm supports image input only",
                    422,
                )
            safe_id = "".join(
                char if char.isalnum() or char in "_.-" else "_"
                for char in media.asset_id
            )
            filename = f"{safe_id.strip('._') or 'asset'}{media.path.suffix.lower()}"
            mime = (
                media.mime_type
                or mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            )
            content = media.path.read_bytes()
            response = await client.post(
                f"{base_url}/shotmill/v1/assets",
                data={"asset_id": media.asset_id, "role": media.role or ""},
                files={"file": (filename, content, mime)},
            )
            _raise_for_comfyui(response, "image upload")
            payload = response.json()
            bridge_asset = payload.get("asset") if isinstance(payload, dict) else None
            remote_name = (
                bridge_asset.get("relativePath")
                if isinstance(bridge_asset, dict)
                else payload.get("name") if isinstance(payload, dict) else None
            )
            if not remote_name:
                raise ShotMillError(
                    "COMFYUI_INVALID_UPLOAD_RESPONSE",
                    "ComfyUI did not return an uploaded prompt asset filename",
                    502,
                )
            uploaded[media.reference] = str(remote_name)
        return uploaded

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        base_url = (
            self.base_url_getter() if self.base_url_getter is not None else self.base_url
        )
        base_url = base_url.rstrip("/") if base_url else None
        if not base_url:
            raise ProviderUnavailableError(
                "ComfyUI endpoint is not configured. Set SHOTMILL_COMFYUI_BASE_URL."
            )
        client_id = f"shotmill-prompt-{uuid4().hex}"
        coordinator_acquired = False
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=self.transport) as client:
                if self.coordinator is not None:
                    await self.coordinator.prepare("prompt", client, base_url)
                    coordinator_acquired = True
                uploaded = await self._upload_assets(client, request, base_url)
                local_settings = (
                    self.settings_getter() if self.settings_getter is not None
                    else LocalInferenceSettings()
                )
                system_prompt = request.system_prompt
                if self.system_prompt_getter is not None:
                    configured_system_prompt = self.system_prompt_getter().system_prompt.strip()
                    if configured_system_prompt:
                        system_prompt = configured_system_prompt
                seed = (
                    local_settings.seed
                    if local_settings.seed_mode == "fixed"
                    else secrets.randbelow(2**63 - 1)
                )
                workflow = _build_workflow(
                    request,
                    uploaded,
                    seed,
                    local_settings,
                    self.model_inputs,
                )
                workflow["1"]["inputs"]["system_prompt"] = system_prompt
                submit = await client.post(
                    f"{base_url}/shotmill/v1/jobs",
                    json={
                        "jobId": client_id,
                        "clientId": client_id,
                        "prompt": workflow,
                    },
                )
                _raise_for_comfyui(submit, "Bridge prompt submission")
                prompt_id = submit.json().get("promptId")
                if not prompt_id:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_INVALID_RESPONSE",
                        "ShotMill IO Bridge did not return promptId for prompt enhancement",
                        502,
                    )

                started = time.monotonic()
                entry: dict[str, Any] | None = None
                while time.monotonic() - started < self.timeout_seconds:
                    state_response = await client.get(
                        f"{base_url}/shotmill/v1/jobs/{client_id}"
                    )
                    _raise_for_comfyui(state_response, "Bridge job status request")
                    state = state_response.json()
                    if state.get("status") == "failed":
                        raise ProviderUnavailableError(
                            "ShotMill IO Bridge prompt enhancement workflow failed"
                        )
                    if state.get("status") == "completed":
                        entry = {"outputs": state.get("nodeOutputs", {})}
                        break
                    await asyncio.sleep(self.poll_interval_seconds)
                if entry is None:
                    raise ShotMillError(
                        "SHOTMILL_BRIDGE_TIMEOUT",
                        "Timed out waiting for ShotMill IO Bridge prompt enhancement",
                        504,
                    )
                outputs = entry.get("outputs") or {}
                text = None
                if isinstance(outputs, dict):
                    for node_id in ("1", "15"):
                        text = _extract_text(outputs.get(node_id))
                        if text:
                            break
                else:
                    text = _extract_text(outputs)
                if not text and isinstance(outputs, dict):
                    text = _extract_text(outputs)
                if not text:
                    raise ShotMillError(
                        "PROMPT_PROVIDER_EMPTY_RESPONSE",
                        "ComfyUI prompt enhancement returned no text",
                        502,
                    )
                text = _clean_model_text(text)
                if not text:
                    raise ShotMillError(
                        "PROMPT_PROVIDER_EMPTY_RESPONSE",
                        "ComfyUI prompt enhancement returned no usable text",
                        502,
                    )
                return PromptAIResponse(
                    text=text,
                    provider_id=self.id,
                    model_id=str(self.model_inputs["model"]),
                )
        except ShotMillError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"ComfyUI prompt request failed: {exc}") from exc
        finally:
            if coordinator_acquired and self.coordinator is not None:
                await self.coordinator.finish()
