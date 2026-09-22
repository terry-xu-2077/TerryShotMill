from __future__ import annotations

import asyncio

from shotmill.app import create_app
from shotmill.devtools.mock_api import MockVideoGenerationProvider
from shotmill.domain.providers import (
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
)
from shotmill.errors import ProviderUnavailableError


class E2EPromptProvider:
    id = "e2e-prompt"
    capability = PromptAIProviderCapability(
        image_input=True,
        native_video_input=True,
        audio_understanding=False,
    )

    def __init__(self) -> None:
        self.failed_once: set[str] = set()

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        user_prompt = next(
            (
                line.removeprefix("用户描述：").strip()
                for line in request.user_text.splitlines()
                if line.startswith("用户描述：")
            ),
            request.user_text.strip(),
        )
        if "E2E_FAIL_ONCE" in user_prompt and user_prompt not in self.failed_once:
            self.failed_once.add(user_prompt)
            raise ProviderUnavailableError("故障注入：首次增强不可用")
        return PromptAIResponse(
            text=f"AI增强预览：{user_prompt}",
            provider_id=self.id,
            model_id="deterministic-e2e",
        )


class E2EVideoProvider(MockVideoGenerationProvider):
    def __init__(self) -> None:
        self.held: dict[str, asyncio.Event] = {}

    async def generate(self, request):
        if "E2E_HOLD_VIDEO" in request.final_prompt:
            release = self.held[request.job_id] = asyncio.Event()
            try:
                await release.wait()
            finally:
                self.held.pop(request.job_id, None)
        return await super().generate(request)


video_provider = E2EVideoProvider()
app = create_app(
    prompt_provider=E2EPromptProvider(), video_provider=video_provider,
)


@app.post("/api/v1/__e2e/videos/{job_id}/release", include_in_schema=False)
async def release_video_fixture(job_id: str):
    # This deterministic barrier exists only in the isolated E2E server.
    release = video_provider.held.get(job_id)
    if release is not None:
        release.set()
    return {"released": release is not None}
