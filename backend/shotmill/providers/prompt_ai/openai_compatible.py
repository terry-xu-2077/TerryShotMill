from __future__ import annotations

import base64
import hashlib
from typing import Any

import httpx

from shotmill.domain.providers import (
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
)
from shotmill.errors import ProviderUnavailableError, ShotMillError


class OpenAICompatiblePromptAIProvider:
    id = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        *,
        supports_native_video: bool = False,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.capability = PromptAIProviderCapability(
            image_input=True,
            native_video_input=supports_native_video,
            sampled_video_frames=False,
            audio_understanding=False,
            system_prompt=True,
            structured_output=False,
        )

    @property
    def display_name(self) -> str:
        return f"API · {self.model}"

    def capture_profile(self) -> dict[str, Any]:
        return {
            "providerId": self.id, "version": 1, "baseUrl": self.base_url,
            "modelId": self.model, "nativeVideo": self.capability.native_video_input,
            "timeoutSeconds": self.timeout_seconds,
            "credentialFingerprint": hashlib.sha256((self.api_key or "").encode()).hexdigest(),
        }

    def bind_profile(self, profile: dict[str, Any]) -> OpenAICompatiblePromptAIProvider:
        if profile.get("credentialFingerprint") != hashlib.sha256(
            (self.api_key or "").encode()
        ).hexdigest():
            raise ShotMillError(
                "PROMPT_CREDENTIAL_CHANGED", "增强服务凭据已变化，请重新提交增强。", 409
            )
        return OpenAICompatiblePromptAIProvider(
            profile["baseUrl"], profile["modelId"], self.api_key,
            supports_native_video=profile["nativeVideo"],
            timeout_seconds=profile["timeoutSeconds"], transport=self.transport,
        )

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        content: list[dict] = [{"type": "text", "text": request.user_text}]
        for media in request.media:
            if media.media_type == "image":
                if not self.capability.image_input:
                    raise ShotMillError(
                        "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                        "Provider does not support images",
                        422,
                    )
                mime = media.mime_type or "image/png"
                encoded = base64.b64encode(media.path.read_bytes()).decode("ascii")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{encoded}"},
                    }
                )
            elif media.media_type == "video":
                if not self.capability.native_video_input:
                    raise ShotMillError(
                        "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                        "Prompt AI provider does not support native video input",
                        422,
                    )
                mime = media.mime_type or "video/mp4"
                encoded = base64.b64encode(media.path.read_bytes()).decode("ascii")
                content.append(
                    {
                        "type": "video_url",
                        "video_url": {"url": f"data:{mime};base64,{encoded}"},
                    }
                )
            elif media.media_type == "audio":
                raise ShotMillError(
                    "PROMPT_PROVIDER_MEDIA_UNSUPPORTED",
                    "Prompt AI provider does not support audio understanding",
                    422,
                )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": content if len(content) > 1 else request.user_text},
            ],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Prompt AI provider request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ShotMillError(
                "PROMPT_PROVIDER_INVALID_RESPONSE",
                "Prompt AI provider returned an invalid response",
                502,
            ) from exc
        try:
            raw_content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ShotMillError(
                "PROMPT_PROVIDER_INVALID_RESPONSE",
                "Prompt AI provider returned an invalid response",
                502,
            ) from exc

        if isinstance(raw_content, str):
            text = raw_content.strip()
        elif isinstance(raw_content, list):
            text = "".join(
                str(part.get("text", "")) for part in raw_content if isinstance(part, dict)
            ).strip()
        else:
            raise ShotMillError(
                "PROMPT_PROVIDER_INVALID_RESPONSE",
                "Prompt AI provider returned an invalid response",
                502,
            )
        if not text:
            raise ShotMillError(
                "PROMPT_PROVIDER_EMPTY_RESPONSE",
                "Prompt AI provider returned an empty prompt",
                502,
            )
        return PromptAIResponse(text=text, provider_id=self.id, model_id=self.model)


class UnavailablePromptAIProvider:
    id = "unconfigured"
    display_name = "未配置增强模型"
    capability = PromptAIProviderCapability(
        image_input=False,
        native_video_input=False,
        sampled_video_frames=False,
        audio_understanding=False,
        system_prompt=True,
        structured_output=False,
    )

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        del request
        raise ProviderUnavailableError(
            "Prompt AI provider is not configured. Set SHOTMILL_PROMPT_AI_BASE_URL "
            "and SHOTMILL_PROMPT_AI_MODEL."
        )
