from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from shotmill.app import create_app
from shotmill.application.prompt_enhancement_service import (
    EnhancementContextOptions,
    EnhancementMedia,
)
from shotmill.application.task_service import SaveTaskAsset, SaveTaskData
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
from shotmill.persistence.migrations import upgrade_database


class MockVideoGenerationProvider:
    """Local playable fixture, using the same persisted execution path as production."""

    id = "shotmill-mock-video"
    capability = VideoGenerationCapability()

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        return VideoGenerationResponse(
            provider_job_id=f"mock-{request.job_id}",
            outputs=(GeneratedOutput(
                filename="preview.mp4",
                content=(Path(__file__).parent / "fixtures" / "preview.mp4").read_bytes(),
                content_type="video/mp4", metadata={"mock": True, "durationSeconds": 2},
            ),),
        )


class MockPromptAIProvider:
    """Deterministic prompt provider for UI and contract development."""

    id = "shotmill-mock-prompt"
    display_name = "演示增强服务"
    capability = PromptAIProviderCapability(
        image_input=True,
        native_video_input=True,
        sampled_video_frames=True,
        audio_understanding=False,
    )

    async def enhance(self, request: PromptAIRequest) -> PromptAIResponse:
        intent = request.user_text.split("\n\n", 1)[0]
        intent = intent.removeprefix("User intent:").strip()
        references = "、".join(item.reference for item in request.media)
        reference_line = f"参考 {references}。" if references else ""
        return PromptAIResponse(
            text=(
                f"{intent}\n"
                f"{reference_line}画面主体清晰，动作连续，镜头运动平稳，"
                "保持光线、人物与空间关系前后一致。"
            ).strip(),
            provider_id=self.id,
            model_id="qwen3.8-mock-contract-v1",
        )


def _svg_asset(title: str, background: str, accent: str) -> bytes:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"
viewBox="0 0 960 540">
<rect width="960" height="540" fill="{background}"/>
<circle cx="720" cy="170" r="120" fill="{accent}" opacity="0.72"/>
<rect x="100" y="110" width="420" height="320" rx="28" fill="#ffffff" opacity="0.12"/>
<text x="100" y="490" fill="#ffffff" font-size="42" font-family="sans-serif">{title}</text>
</svg>""".encode()


def _settings(data_root: Path) -> Settings:
    resolved = data_root.resolve()
    return Settings(
        app_name="ShotMill Mock API",
        api_version="0.4-mock",
        data_root=resolved,
        database_url=f"sqlite+pysqlite:///{(resolved / 'shotmill-mock.db').as_posix()}",
        auto_migrate=True,
        generation_workers=1,
        provider_poll_interval_seconds=0.01,
        provider_timeout_seconds=5.0,
    )


async def seed_mock_scenario(application: FastAPI) -> None:
    container = application.state.container
    if container.workspace_query.list_projects():
        return

    project = container.project_service.create(
        "雨夜仓库 · Mock 项目",
        "一支悬疑氛围短片。冷色雨夜与仓库内暖光形成对比，人物和场景需要保持连续。",
        True,
    )
    character = container.asset_service.import_bytes(
        project.id,
        "linlan-rain.svg",
        _svg_asset("林澜 · 雨夜造型", "#19233c", "#d79658"),
        content_type="image/svg+xml",
        name="林澜 · 雨夜造型",
        category="character",
        tags=["林澜", "主角", "雨夜"],
    )
    scene = container.asset_service.import_bytes(
        project.id,
        "warehouse-night.svg",
        _svg_asset("旧港口仓库外景", "#172b2f", "#8bb8aa"),
        content_type="image/svg+xml",
        name="旧港口仓库外景",
        category="scene",
        tags=["仓库", "港口", "夜景"],
    )
    container.task_service.create(
        project.id,
        SaveTaskData(
            title="抵达仓库",
            summary="林澜穿过雨夜码头，在仓库门前停下。",
            script_source="雨声渐密，她撑伞穿过潮湿码头，停在仓库门前。",
            user_intent="由远及近建立空间，最后停在人物发现门缝暖光的瞬间。",
            user_prompt=(
                "<Picture 1>中的人物撑伞穿过雨夜码头，<Picture 2>作为仓库外景。"
                "镜头从全景缓慢推进到中近景，门缝透出暖光，雨丝清晰可见。"
            ),
            prompt_source="user",
            duration_seconds=8,
            generation={
                "resolution": "1080p",
                "quality": "标准",
                "mode": "全能参考",
                "contextMode": "不承接",
            },
            asset_bindings=(
                SaveTaskAsset(character.id, "<Picture 1>", "character"),
                SaveTaskAsset(scene.id, "<Picture 2>", "scene"),
            ),
        ),
    )
    second = container.task_service.create(
        project.id,
        SaveTaskData(
            title="推门进入",
            summary="人物推开门，仓库深处的放映机自行亮起。",
            script_source="她推开门。黑暗深处，一束放映机光线突然亮起。",
            user_intent="承接上一任务的雨夜氛围，动作克制，不使用跳吓。",
            user_prompt=(
                "<Picture 1>中的人物推开仓库木门，镜头越过肩膀看向室内，"
                "黑暗深处逐渐亮起一束放映机光线。"
            ),
            prompt_source="ai",
            duration_seconds=6,
            generation={
                "resolution": "1080p",
                "quality": "标准",
                "mode": "全能参考",
                "contextMode": "尾帧承接",
            },
            asset_bindings=(SaveTaskAsset(character.id, "<Picture 1>", "character"),),
        ),
    )
    await container.prompt_enhancement_service.enhance(
        project.id,
        second.id,
        target="minimax-h3",
        user_prompt=second.user_prompt,
        media=(EnhancementMedia(character.id, "<Picture 1>", "character"),),
        context=EnhancementContextOptions(
            include_project_background=True,
            include_previous_task_summary=True,
        ),
        duration_seconds=second.planned_duration_seconds,
        mode="全能参考",
        context_mode="尾帧承接",
    )
    container.task_service.create(
        project.id,
        SaveTaskData(
            title="待补充任务",
            summary="用于检查空白和未完成状态。",
            user_prompt="补充镜头动作与构图，保持雨夜仓库的连续氛围。",
            duration_seconds=6,
        ),
    )


async def create_mock_app(data_root: Path) -> FastAPI:
    selected_settings = _settings(data_root)
    selected_settings.data_root.mkdir(parents=True, exist_ok=True)
    upgrade_database(selected_settings.database_url)
    application = create_app(
        selected_settings,
        prompt_provider=MockPromptAIProvider(),
        video_provider=MockVideoGenerationProvider(),
    )
    await seed_mock_scenario(application)
    return application
