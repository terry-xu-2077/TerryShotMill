from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class PromptAIProviderCapability:
    image_input: bool = True
    native_video_input: bool = False
    sampled_video_frames: bool = False
    audio_understanding: bool = False
    system_prompt: bool = True
    structured_output: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedMedia:
    asset_id: str
    reference: str
    role: str | None
    media_type: str
    path: Path
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class PromptAIRequest:
    system_prompt: str
    user_text: str
    media: tuple[ResolvedMedia, ...] = ()


@dataclass(frozen=True, slots=True)
class PromptAIResponse:
    text: str
    provider_id: str
    model_id: str | None = None


class PromptAIProvider(Protocol):
    id: str
    capability: PromptAIProviderCapability

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse: ...


@runtime_checkable
class SnapshotPromptAIProvider(PromptAIProvider, Protocol):
    """Provider-owned, serializable execution configuration; excludes credentials."""

    def capture_profile(self) -> dict[str, Any]: ...
    def bind_profile(self, profile: dict[str, Any]) -> PromptAIProvider: ...


@dataclass(frozen=True, slots=True)
class VideoGenerationCapability:
    text: bool = True
    image: bool = True
    first_frame: bool = True
    last_frame: bool = True
    reference_images: bool = True
    reference_videos: bool = True
    max_duration_seconds: float | None = None
    continuation: bool = True
    progress_reporting: bool = True
    batch: bool = False
    max_concurrency: int = 1
    job_resumption: bool = False


@dataclass(frozen=True, slots=True)
class VideoGenerationRequest:
    job_id: str
    project_id: str
    task_id: str
    final_prompt: str
    assets: tuple[ResolvedMedia, ...]
    params: dict[str, Any]
    seed: int | None = None


@dataclass(frozen=True, slots=True)
class GeneratedOutput:
    filename: str
    content: bytes
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VideoGenerationResponse:
    provider_job_id: str
    outputs: tuple[GeneratedOutput, ...]


@runtime_checkable
class ProgressReportingVideoProvider(Protocol):
    def set_progress_callback(self, callback) -> None: ...


@runtime_checkable
class StoppableVideoProvider(Protocol):
    async def stop(self, job_id: str) -> None: ...


class VideoGenerationProvider(Protocol):
    id: str
    capability: VideoGenerationCapability

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResponse: ...


@runtime_checkable
class ResumableVideoGenerationProvider(VideoGenerationProvider, Protocol):
    """Observe/collect an existing logical job; never submit new generation on resume."""

    async def resume(self, job_id: str) -> VideoGenerationResponse: ...


@runtime_checkable
class ValidatingVideoGenerationProvider(VideoGenerationProvider, Protocol):
    """Read-only provider validation; must not upload media or start generation."""

    async def validate(self, request: VideoGenerationRequest) -> dict[str, Any] | None:
        """Return provider-owned execution snapshot additions after successful validation."""
        ...


@runtime_checkable
class SnapshotVideoGenerationProvider(VideoGenerationProvider, Protocol):
    def capture_profile(self, request: VideoGenerationRequest) -> dict[str, Any]: ...
    def bind_profile(self, profile: dict[str, Any]) -> VideoGenerationProvider: ...
