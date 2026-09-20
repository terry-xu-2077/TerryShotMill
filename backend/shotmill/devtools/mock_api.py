from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, status

from shotmill.api.schemas import BatchPromptEnhancementRequest, VideoBatchRequest
from shotmill.app import create_app
from shotmill.application.prompt_enhancement_service import (
    EnhancementContextOptions,
    EnhancementMedia,
)
from shotmill.application.task_service import SaveTaskAsset, SaveTaskData
from shotmill.config import Settings
from shotmill.domain.providers import (
    PromptAIProviderCapability,
    PromptAIRequest,
    PromptAIResponse,
)
from shotmill.frontend_adapter.models import (
    ApiModel,
    BatchPromptEnhancementItemView,
    BatchPromptEnhancementResponse,
    PromptReviewItemView,
    PromptReviewStateView,
    VideoBatchEligibilityView,
    VideoBatchResponse,
    VideoBatchSkippedItem,
)
from shotmill.persistence.migrations import upgrade_database


class MockPromptAIProvider:
    """Deterministic prompt provider for UI and contract development."""

    id = "shotmill-mock-prompt"
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


class MockBatchPromptRequest(ApiModel):
    task_ids: list[str]
    include_project_background: bool = True
    include_previous_task_summary: bool = True


class MockBatchPromptItem(ApiModel):
    task_id: str
    state: str
    revision_id: str | None = None
    error: str | None = None


class MockBatchPromptResponse(ApiModel):
    batch_id: str
    state: str
    items: list[MockBatchPromptItem]


class MockPromptReviewRequest(ApiModel):
    action: str = "approve"


class MockPromptReviewItem(ApiModel):
    task_id: str
    prompt_review_status: str
    approved_revision: int | None = None


class MockPromptReviewList(ApiModel):
    items: list[MockPromptReviewItem]


class MockVideoBatchRequest(ApiModel):
    task_ids: list[str]


class MockVideoBatchSkip(ApiModel):
    task_id: str
    reason: str


class MockVideoBatchEligibility(ApiModel):
    eligible_task_ids: list[str]
    skipped: list[MockVideoBatchSkip]


class MockVideoBatchResponse(MockVideoBatchEligibility):
    batch_id: str


def _install_mock_batch_routes(application: FastAPI) -> None:
    batch_prefixes = (
        "/prompt-review",
        "/prompt-enhancement-batches",
        "/video-generation-batches",
    )

    def is_batch_router(route) -> bool:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            return any(is_batch_router(child) for child in original_router.routes)
        path = getattr(route, "path", "")
        return any(prefix in path for prefix in batch_prefixes)

    application.router.routes[:] = [
        route for route in application.router.routes if not is_batch_router(route)
    ]
    application.state.mock_prompt_reviews = {}
    application.state.mock_prompt_batches = {}

    @application.post(
        "/api/v1/projects/{project_id}/prompt-enhancement-batches",
        response_model=BatchPromptEnhancementResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["batch-review"],
    )
    async def create_prompt_enhancement_batch(
        project_id: str,
        payload: BatchPromptEnhancementRequest,
    ) -> BatchPromptEnhancementResponse:
        container = application.state.container
        items: list[BatchPromptEnhancementItemView] = []
        for task_id in payload.task_ids:
            try:
                editor = container.workspace_query.task_editor(project_id, task_id)
                revision = await container.prompt_enhancement_service.enhance(
                    project_id,
                    task_id,
                    target="minimax-h3",
                    user_prompt=editor.user_prompt,
                    media=tuple(
                        EnhancementMedia(binding.asset_id, binding.reference, binding.role)
                        for binding in editor.asset_bindings
                    ),
                    context=EnhancementContextOptions(
                        include_project_background=payload.include_project_background,
                        include_previous_task_summary=payload.include_previous_task_summary,
                    ),
                    duration_seconds=editor.duration_seconds,
                    mode=editor.generation.mode,
                    context_mode=editor.generation.context_mode,
                )
                application.state.mock_prompt_reviews.pop(task_id, None)
                items.append(
                    BatchPromptEnhancementItemView(
                        task_id=task_id,
                        state="completed",
                        revision_id=revision.id,
                    )
                )
            except Exception as exc:
                items.append(
                    BatchPromptEnhancementItemView(
                        task_id=task_id,
                        state="failed",
                        error=str(exc),
                    )
                )

        completed = sum(item.state == "completed" for item in items)
        state = (
            "completed"
            if completed == len(items)
            else "failed"
            if completed == 0
            else "partial"
        )
        response = BatchPromptEnhancementResponse(
            batch_id=f"promptbatch-{uuid4().hex[:12]}",
            state=state,
            items=items,
        )
        application.state.mock_prompt_batches[response.batch_id] = response
        return response

    @application.get(
        "/api/v1/projects/{project_id}/prompt-enhancement-batches/{batch_id}",
        response_model=BatchPromptEnhancementResponse,
        tags=["batch-review"],
    )
    async def get_prompt_enhancement_batch(
        project_id: str,
        batch_id: str,
    ) -> BatchPromptEnhancementResponse:
        return application.state.mock_prompt_batches[batch_id]

    @application.get(
        "/api/v1/projects/{project_id}/prompt-review-state",
        response_model=PromptReviewStateView,
        tags=["batch-review"],
    )
    async def get_prompt_review_state(project_id: str) -> PromptReviewStateView:
        container = application.state.container
        reviews: dict[str, int] = application.state.mock_prompt_reviews
        workspace = container.workspace_query.workspace(project_id)
        items: list[PromptReviewItemView] = []
        for task in workspace.tasks:
            editor = container.workspace_query.task_editor(project_id, task.id)
            approved_revision = reviews.get(task.id)
            approved = approved_revision == editor.revision
            items.append(
                PromptReviewItemView(
                    task_id=task.id,
                    prompt_review_status="approved" if approved else "pending_review",
                    approved_revision=approved_revision if approved else None,
                )
            )
        return PromptReviewStateView(items=items)

    @application.post(
        "/api/v1/projects/{project_id}/tasks/{task_id}/prompt-review/approve",
        response_model=PromptReviewItemView,
        tags=["batch-review"],
    )
    @application.post(
        "/api/v1/projects/{project_id}/tasks/{task_id}/prompt-review",
        response_model=PromptReviewItemView,
        tags=["batch-review"],
    )
    async def approve_prompt(
        project_id: str,
        task_id: str,
    ) -> PromptReviewItemView:
        editor = application.state.container.workspace_query.task_editor(project_id, task_id)
        application.state.mock_prompt_reviews[task_id] = editor.revision
        return PromptReviewItemView(
            task_id=task_id,
            prompt_review_status="approved",
            approved_revision=editor.revision,
        )

    def evaluate_video_batch(project_id: str, task_ids: list[str]) -> VideoBatchEligibilityView:
        container = application.state.container
        reviews: dict[str, int] = application.state.mock_prompt_reviews
        eligible: list[str] = []
        skipped: list[VideoBatchSkippedItem] = []
        for task_id in task_ids:
            try:
                editor = container.workspace_query.task_editor(project_id, task_id)
            except Exception:
                skipped.append(VideoBatchSkippedItem(task_id=task_id, reason="invalid-params"))
                continue
            if reviews.get(task_id) != editor.revision:
                skipped.append(VideoBatchSkippedItem(task_id=task_id, reason="not-reviewed"))
                continue
            eligible.append(task_id)
        return VideoBatchEligibilityView(eligible_task_ids=eligible, skipped=skipped)

    @application.post(
        "/api/v1/projects/{project_id}/video-generation-batches/eligibility",
        response_model=VideoBatchEligibilityView,
        tags=["batch-review"],
    )
    async def check_video_batch_eligibility(
        project_id: str,
        payload: VideoBatchRequest,
    ) -> VideoBatchEligibilityView:
        return evaluate_video_batch(project_id, payload.task_ids)

    @application.post(
        "/api/v1/projects/{project_id}/video-generation-batches",
        response_model=VideoBatchResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["batch-review"],
    )
    async def create_video_generation_batch(
        project_id: str,
        payload: VideoBatchRequest,
    ) -> VideoBatchResponse:
        eligibility = evaluate_video_batch(project_id, payload.task_ids)
        return VideoBatchResponse(
            batch_id=f"videobatch-{uuid4().hex[:12]}",
            eligible_task_ids=eligibility.eligible_task_ids,
            skipped=eligibility.skipped,
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
    )
    _install_mock_batch_routes(application)
    await seed_mock_scenario(application)
    return application
