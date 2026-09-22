from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shotmill.app import create_app
from shotmill.config import Settings
from shotmill.domain.providers import (
    GeneratedOutput,
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
    VideoGenerationCapability,
    VideoGenerationRequest,
    VideoGenerationResponse,
)


@pytest.fixture
def bridge_snapshot():
    def make(workflow_id="w.json", inputs=None, prompt=None):
        prompt = prompt or {"1": {"class_type": "PrimitiveInt", "inputs": {"value": 17}}}
        content = {
            "version": 1, "workflowId": workflow_id, "raw": {"prompt": prompt},
            "prompt": prompt, "inputs": inputs or [],
        }
        encoded = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return {**content, "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}

    return make


class FakePromptProvider:
    id = "fake-prompt"
    capability = PromptAIProviderCapability(
        image_input=True,
        native_video_input=True,
        sampled_video_frames=False,
        audio_understanding=False,
        system_prompt=True,
        structured_output=False,
    )

    def __init__(self) -> None:
        self.requests: list[PromptAIRequest] = []

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        self.requests.append(request)
        media_refs = ",".join(item.reference for item in request.media)
        return PromptAIResponse(
            text=f"ENHANCED::{request.user_text.splitlines()[1]}::{media_refs}",
            provider_id=self.id,
            model_id="fake-model",
        )


class FakeVideoProvider:
    id = "fake-video"
    capability = VideoGenerationCapability(max_duration_seconds=15, max_concurrency=1)

    def __init__(self) -> None:
        self.requests: list[VideoGenerationRequest] = []

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        self.requests.append(request)
        return VideoGenerationResponse(
            provider_job_id=f"provider-{request.job_id}",
            outputs=(
                GeneratedOutput(
                    filename="result.mp4",
                    content=b"fake-video-bytes",
                    content_type="video/mp4",
                    metadata={"fake": True},
                ),
            ),
        )


@pytest.fixture
def providers():
    return FakePromptProvider(), FakeVideoProvider()


@pytest.fixture
def client(tmp_path: Path, providers):
    prompt_provider, video_provider = providers
    data_root = tmp_path / "data"
    settings = Settings(
        app_name="ShotMill",
        api_version="0.3",
        data_root=data_root,
        database_url=f"sqlite+pysqlite:///{(data_root / 'test.db').as_posix()}",
        auto_migrate=True,
        generation_workers=1,
    )
    app = create_app(settings, prompt_provider=prompt_provider, video_provider=video_provider)
    with TestClient(app) as test_client:
        yield test_client
