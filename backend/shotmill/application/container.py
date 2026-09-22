from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from shotmill.application.application_settings import ApplicationSettingsStore
from shotmill.application.asset_service import AssetService
from shotmill.application.batch_service import BatchProductionService, PromptEnhancementQueue
from shotmill.application.event_bus import ProjectEventBus
from shotmill.application.generation_service import GenerationQueue, GenerationService
from shotmill.application.project_service import ProjectService
from shotmill.application.prompt_enhancement_service import PromptEnhancementService
from shotmill.application.prompt_review import PromptReviewService
from shotmill.application.result_service import ResultService
from shotmill.application.task_service import TaskService
from shotmill.application.workspace_query import WorkspaceQuery
from shotmill.config import Settings
from shotmill.domain.application_settings import ComfyUISettings
from shotmill.domain.providers import PromptAIProvider, VideoGenerationProvider
from shotmill.errors import ShotMillError
from shotmill.media.resolver import MediaResolver
from shotmill.media.storage import MediaStorage
from shotmill.persistence.database import create_database_engine, create_session_factory
from shotmill.persistence.repositories import SqlAlchemyUnitOfWork
from shotmill.prompt_skills.registry import PromptSkillRegistry
from shotmill.providers.comfyui_runtime import ComfyUIExecutionCoordinator
from shotmill.providers.prompt_ai.comfyui import ComfyUIPromptAIProvider
from shotmill.providers.prompt_ai.configurable import ConfigurablePromptAIProvider
from shotmill.providers.prompt_ai.openai_compatible import (
    OpenAICompatiblePromptAIProvider,
    UnavailablePromptAIProvider,
)
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    application_settings: ApplicationSettingsStore
    engine: Engine
    session_factory: sessionmaker[Session]
    storage: MediaStorage
    events: ProjectEventBus
    project_service: ProjectService
    asset_service: AssetService
    task_service: TaskService
    workspace_query: WorkspaceQuery
    prompt_enhancement_service: PromptEnhancementService
    prompt_review_service: PromptReviewService
    batch_production_service: BatchProductionService
    prompt_enhancement_queue: PromptEnhancementQueue
    generation_service: GenerationService
    generation_queue: GenerationQueue
    result_service: ResultService


def build_container(
    settings: Settings,
    *,
    prompt_provider: PromptAIProvider | None = None,
    video_provider: VideoGenerationProvider | None = None,
) -> ApplicationContainer:
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    application_settings = ApplicationSettingsStore(
        settings.data_root / "application-settings.json",
        comfyui_defaults=ComfyUISettings(
            base_url=settings.comfyui_base_url or "http://127.0.0.1:8188",
            root_path=str(settings.comfyui_root or ""),
        ),
    )
    comfyui_coordinator = ComfyUIExecutionCoordinator()

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    storage = MediaStorage(settings.projects_root)
    resolver = MediaResolver(storage)
    events = ProjectEventBus()
    if prompt_provider is None:
        local_prompt_provider = ComfyUIPromptAIProvider(
                settings.comfyui_base_url,
                poll_interval_seconds=settings.provider_poll_interval_seconds,
                timeout_seconds=settings.provider_timeout_seconds,
                settings_getter=application_settings.get_local_inference,
                system_prompt_getter=application_settings.get_prompt_system,
                base_url_getter=lambda: application_settings.get_comfyui().base_url,
                use_bridge_assets=True,
                coordinator=comfyui_coordinator,
            )
        api_prompt_provider = (
            OpenAICompatiblePromptAIProvider(
                settings.prompt_ai_base_url,
                settings.prompt_ai_model,
                settings.prompt_ai_api_key,
                supports_native_video=settings.prompt_ai_supports_native_video,
            )
            if settings.prompt_ai_base_url and settings.prompt_ai_model
            else UnavailablePromptAIProvider()
        )

        def api_provider_factory(prompt_settings):
            base_url = prompt_settings.api_base_url or settings.prompt_ai_base_url
            model = prompt_settings.api_model or settings.prompt_ai_model
            if not base_url or not model:
                return UnavailablePromptAIProvider()
            return OpenAICompatiblePromptAIProvider(
                base_url,
                model,
                prompt_settings.api_key or settings.prompt_ai_api_key,
                supports_native_video=(
                    prompt_settings.api_supports_native_video
                    or settings.prompt_ai_supports_native_video
                ),
            )

        prompt_provider = ConfigurablePromptAIProvider(
            local_prompt_provider,
            api_prompt_provider,
            application_settings.get_prompt_system,
            api_provider_factory=api_provider_factory,
        )
    if video_provider is None:
        def workflow_profile_getter(request):
            comfyui = application_settings.get_comfyui()
            requested_id = str(
                request.params.get("workflowProfileId")
                or request.params.get("profileId")
                or ""
            )
            profile = next(
                (
                    item
                    for item in comfyui.workflow_profiles
                    if item.enabled and item.id == requested_id
                ),
                None,
            )
            if requested_id and (profile is None or not profile.workflow_file):
                raise ShotMillError(
                    "WORKFLOW_PROFILE_UNAVAILABLE",
                    "任务选择的工作流已删除、停用或未配置文件，请重新选择。",
                    422,
                )
            if profile is None and comfyui.default_profile_id:
                profile = next(
                    (
                        item
                        for item in comfyui.workflow_profiles
                        if item.enabled and item.id == comfyui.default_profile_id
                    ),
                    None,
                )
            if profile is None:
                resolution = str(request.params.get("resolution", ""))
                quality = str(request.params.get("quality", ""))
                profile = next(
                    (
                        item
                        for item in comfyui.workflow_profiles
                        if item.enabled
                        and (not item.resolution or item.resolution == resolution)
                        and (not item.quality or item.quality == quality)
                    ),
                    None,
                )
            return profile

        def workflow_path_getter(request):
            profile = workflow_profile_getter(request)
            comfyui = application_settings.get_comfyui()
            if profile is None or not profile.workflow_file:
                return None
            workflow_file = Path(profile.workflow_file).expanduser()
            if not workflow_file.is_absolute():
                workflow_file = (
                    Path(comfyui.root_path).expanduser()
                    / comfyui.workflow_directory
                    / workflow_file
                )
            return workflow_file

        video_provider = ComfyUIVideoGenerationProvider(
            settings.comfyui_base_url,
            settings.comfyui_workflow_template,
            poll_interval_seconds=settings.provider_poll_interval_seconds,
            timeout_seconds=settings.provider_timeout_seconds,
            coordinator=comfyui_coordinator,
            base_url_getter=lambda: application_settings.get_comfyui().base_url,
            workflow_path_getter=workflow_path_getter,
            numeric_bindings_getter=lambda request: (
                profile.numeric_bindings if (profile := workflow_profile_getter(request)) else ()
            ),
            use_bridge_assets=True,
        )

    project_service = ProjectService(uow_factory, storage)
    asset_service = AssetService(uow_factory, storage)
    task_service = TaskService(uow_factory, storage)
    workspace_query = WorkspaceQuery(uow_factory, storage)
    prompt_enhancement_service = PromptEnhancementService(
        uow_factory,
        prompt_provider,
        PromptSkillRegistry(),
        resolver,
    )
    prompt_review_service = PromptReviewService(uow_factory)
    generation_service = GenerationService(uow_factory, video_provider, storage, events)
    generation_queue = GenerationQueue(generation_service, settings.generation_workers)
    generation_service.attach_queue(generation_queue)
    batch_production_service = BatchProductionService(
        uow_factory,
        prompt_enhancement_service,
        generation_service,
        events=events,
    )
    prompt_enhancement_queue = PromptEnhancementQueue(
        batch_production_service,
        settings.prompt_enhancement_workers,
    )
    batch_production_service.attach_queue(prompt_enhancement_queue)
    result_service = ResultService(uow_factory)
    return ApplicationContainer(
        settings=settings,
        application_settings=application_settings,
        engine=engine,
        session_factory=session_factory,
        storage=storage,
        events=events,
        project_service=project_service,
        asset_service=asset_service,
        task_service=task_service,
        workspace_query=workspace_query,
        prompt_enhancement_service=prompt_enhancement_service,
        prompt_review_service=prompt_review_service,
        batch_production_service=batch_production_service,
        prompt_enhancement_queue=prompt_enhancement_queue,
        generation_service=generation_service,
        generation_queue=generation_queue,
        result_service=result_service,
    )
