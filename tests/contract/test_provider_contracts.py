import asyncio
import json
from pathlib import Path

import httpx
import pytest
from shotmill.domain.providers import PromptAIRequest, ResolvedMedia, VideoGenerationRequest
from shotmill.errors import ProviderUnavailableError, ShotMillError
from shotmill.prompt_skills.base import SkillInput
from shotmill.prompt_skills.minimax_h3 import MiniMaxH3PromptSkill
from shotmill.prompt_skills.seedance_2 import Seedance2PromptSkill
from shotmill.providers.prompt_ai.openai_compatible import (
    OpenAICompatiblePromptAIProvider,
)
from shotmill.providers.video_generation.comfyui import (
    ComfyUIVideoGenerationProvider,
    _prune_missing_optional_assets,
    _replace_placeholders,
)


def test_prompt_skills_remain_target_specific() -> None:
    data = SkillInput(
        user_prompt="角色奔跑",
        project_background=None,
        previous_task_summary=None,
        duration_seconds=6,
        mode="全能参考",
        context_mode="不承接",
        media=(),
    )
    h3 = MiniMaxH3PromptSkill().build(data)
    seedance = Seedance2PromptSkill().build(data)
    assert "# Full-Reference Mode Rewrite Output Format Guide" in h3.system_prompt
    assert "Write all six rewrite sections in English" in h3.system_prompt
    assert "subject_definitions" in h3.system_prompt
    assert "Seedance" in seedance.system_prompt
    assert h3.system_prompt != seedance.system_prompt


def test_openai_compatible_prompt_provider_sends_system_text_and_real_image(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"real-image-bytes")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": " enhanced prompt "}}]},
        )

    provider = OpenAICompatiblePromptAIProvider(
        "http://prompt.local/v1",
        "vision-model",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        provider.enhance(
            PromptAIRequest(
                system_prompt="H3 system rules",
                user_text="用户描述：角色奔跑",
                media=(
                    ResolvedMedia(
                        asset_id="asset-1",
                        reference="<Picture 1>",
                        role="character",
                        media_type="image",
                        path=image_path,
                        mime_type="image/png",
                    ),
                ),
            )
        )
    )

    assert provider.capability.image_input is True
    assert provider.capability.audio_understanding is False
    assert response.text == "enhanced prompt"
    assert captured["messages"][0] == {
        "role": "system",
        "content": "H3 system rules",
    }
    user_content = captured["messages"][1]["content"]
    assert user_content[0] == {"type": "text", "text": "用户描述：角色奔跑"}
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openai_compatible_prompt_provider_native_video_is_capability_driven(
    tmp_path: Path,
) -> None:
    video_path = tmp_path / "reference.mp4"
    video_path.write_bytes(b"real-video-bytes")
    media = ResolvedMedia(
        asset_id="asset-video",
        reference="<Video 1>",
        role="motion",
        media_type="video",
        path=video_path,
        mime_type="video/mp4",
    )
    request = PromptAIRequest(system_prompt="rules", user_text="prompt", media=(media,))

    unsupported = OpenAICompatiblePromptAIProvider(
        "http://prompt.local/v1",
        "text-model",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "unused"}}]})
        ),
    )
    with pytest.raises(ShotMillError, match="native video") as unsupported_error:
        asyncio.run(unsupported.enhance(request))
    assert unsupported_error.value.code == "PROMPT_PROVIDER_MEDIA_UNSUPPORTED"

    captured: dict = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(http_request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "video prompt"}}]})

    supported = OpenAICompatiblePromptAIProvider(
        "http://prompt.local/v1",
        "video-model",
        supports_native_video=True,
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(supported.enhance(request))
    assert response.text == "video prompt"
    assert supported.capability.native_video_input is True
    assert captured["messages"][1]["content"][1]["video_url"]["url"].startswith(
        "data:video/mp4;base64,"
    )


@pytest.mark.parametrize("status_code", [401, 429, 503])
def test_openai_compatible_prompt_provider_normalizes_http_failures(
    status_code: int,
) -> None:
    provider = OpenAICompatiblePromptAIProvider(
        "http://prompt.local/v1",
        "model",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, json={"error": "provider failure"})
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.enhance(PromptAIRequest(system_prompt="rules", user_text="prompt")))


def test_openai_compatible_prompt_provider_normalizes_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timeout", request=request)

    provider = OpenAICompatiblePromptAIProvider(
        "http://prompt.local/v1",
        "model",
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.enhance(PromptAIRequest(system_prompt="rules", user_text="prompt")))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": {}}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
    ],
)
def test_openai_compatible_prompt_provider_rejects_invalid_responses(
    response: httpx.Response,
) -> None:
    provider = OpenAICompatiblePromptAIProvider(
        "http://prompt.local/v1",
        "model",
        transport=httpx.MockTransport(lambda _: response),
    )
    with pytest.raises(ShotMillError) as error:
        asyncio.run(provider.enhance(PromptAIRequest(system_prompt="rules", user_text="prompt")))
    assert error.value.code in {
        "PROMPT_PROVIDER_INVALID_RESPONSE",
        "PROMPT_PROVIDER_EMPTY_RESPONSE",
    }


def test_comfyui_template_replacement_preserves_typed_values(tmp_path: Path) -> None:
    media_path = tmp_path / "frame.png"
    media_path.write_bytes(b"image")
    request = VideoGenerationRequest(
        job_id="job-1",
        project_id="project-1",
        task_id="task-1",
        final_prompt="cinematic prompt",
        assets=(
            ResolvedMedia(
                asset_id="asset-1",
                reference="<Picture 1>",
                role="first frame",
                media_type="image",
                path=media_path,
                mime_type="image/png",
            ),
        ),
        params={"steps": 12},
        seed=123,
    )
    rendered = _replace_placeholders(
        {
            "prompt": "{{final_prompt}}",
            "seed": "{{seed}}",
            "steps": "{{param:steps}}",
            "asset": "{{asset:<Picture 1>}}",
        },
        request,
    )
    assert rendered["prompt"] == "cinematic prompt"
    assert rendered["seed"] == 123
    assert rendered["steps"] == 12
    assert rendered["asset"] == str(media_path)


def test_comfyui_optional_asset_slots_are_pruned_with_dangling_inputs(
    tmp_path: Path,
) -> None:
    request = VideoGenerationRequest(
        job_id="job-1",
        project_id="project-1",
        task_id="task-1",
        final_prompt="prompt",
        assets=(),
        params={},
    )
    workflow = {
        "load": {
            "inputs": {"image": "{{asset?:<Picture 1>}}"},
            "class_type": "LoadImage",
        },
        "consumer": {
            "inputs": {"prompt": "{{final_prompt}}", "image": ["load", 0]},
            "class_type": "VideoNode",
        },
    }

    pruned = _prune_missing_optional_assets(workflow, request)

    assert "load" not in pruned
    assert pruned["consumer"]["inputs"] == {"prompt": "{{final_prompt}}"}


def test_comfyui_provider_uploads_assets_submits_and_collects_video(
    tmp_path: Path,
) -> None:
    media_path = tmp_path / "frame.png"
    media_path.write_bytes(b"image-bytes")
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "load": {
                    "inputs": {"image": "{{asset?:<Picture 1>}}"},
                    "class_type": "LoadImage",
                },
                "generate": {
                    "inputs": {
                        "prompt": "{{final_prompt}}",
                        "seed": "{{seed}}",
                        "duration": "{{param:durationSeconds}}",
                        "image": ["load", 0],
                    },
                    "class_type": "VideoNode",
                },
                "save": {
                    "inputs": {
                        "filename_prefix": "video/shotmill_{{job_id}}",
                        "video": ["generate", 0],
                    },
                    "class_type": "SaveVideo",
                },
            }
        ),
        encoding="utf-8",
    )
    submitted: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/shotmill/v1/assets":
            assert b"image-bytes" in request.content
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "asset": {
                        "assetId": "asset-1",
                        "relativePath": "shotmill/assets/asset-1/asset-1.png",
                    },
                },
            )
        if request.url.path == "/shotmill/v1/workflows":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "workflows": [
                        {
                            "id": "workflow.json",
                            "relativePath": "workflow.json",
                            "inputs": [{"name": "image", "direction": "input", "type": "IMAGE"}],
                        }
                    ],
                },
            )
        if request.url.path == "/shotmill/v1/jobs":
            payload = json.loads(request.content)
            submitted.update(payload)
            return httpx.Response(200, json={"jobId": "job-1", "promptId": "prompt-1"})
        if request.url.path == "/shotmill/v1/jobs/job-1":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "jobId": "job-1",
                    "promptId": "prompt-1",
                    "status": "completed",
                    "results": [
                        {
                            "filename": "shotmill_job-1.mp4",
                            "relativePath": "shotmill/results/job-1/shotmill_job-1.mp4",
                        }
                    ],
                },
            )
        if request.url.path == "/shotmill/v1/results/job-1/files/0":
            return httpx.Response(
                200,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = ComfyUIVideoGenerationProvider(
        "http://comfy.test",
        workflow_path,
        poll_interval_seconds=0.1,
        transport=httpx.MockTransport(handler),
    )
    request = VideoGenerationRequest(
        job_id="job-1",
        project_id="project-1",
        task_id="task-1",
        final_prompt="cinematic prompt",
        assets=(
            ResolvedMedia(
                asset_id="asset-1",
                reference="<Picture 1>",
                role="reference",
                media_type="image",
                path=media_path,
                mime_type="image/png",
            ),
        ),
        params={"durationSeconds": 6},
        seed=123,
    )

    response = asyncio.run(provider.generate(request))

    assert submitted["workflowId"] == "workflow.json"
    assert submitted["finalPrompt"] == "cinematic prompt"
    assert submitted["seed"] == 123
    assert submitted["params"] == {"durationSeconds": 6}
    assert submitted["assetValues"]["<Picture 1>"] == "shotmill/assets/asset-1/asset-1.png"
    assert response.provider_job_id == "prompt-1"
    assert response.outputs[0].content == b"video-bytes"
    assert response.outputs[0].content_type == "video/mp4"
