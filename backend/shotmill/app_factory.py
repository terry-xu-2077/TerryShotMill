from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from shotmill.api import (
    application_settings,
    assets,
    batch_review,
    comfyui,
    events,
    generation,
    project_transfer,
    projects,
    prompt_enhancements,
    removal,
    results,
    shared_media,
    tasks,
)
from shotmill.application.container import build_container
from shotmill.config import Settings, settings
from shotmill.domain.providers import PromptAIProvider, VideoGenerationProvider
from shotmill.errors import ShotMillError


def create_app(
    app_settings: Settings | None = None,
    *,
    prompt_provider: PromptAIProvider | None = None,
    video_provider: VideoGenerationProvider | None = None,
) -> FastAPI:
    selected_settings = app_settings or settings
    container = build_container(
        selected_settings,
        prompt_provider=prompt_provider,
        video_provider=video_provider,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        selected_settings.data_root.mkdir(parents=True, exist_ok=True)
        container.project_documents.load_recent()
        await run_in_threadpool(container.project_export_service.recover_abandoned)
        await container.prompt_enhancement_queue.start()
        await container.generation_queue.start()
        try:
            yield
        finally:
            await run_in_threadpool(container.project_export_downloads.close)
            await container.generation_queue.stop()
            await container.prompt_enhancement_queue.stop()
            container.engine.dispose()

    application = FastAPI(
        title=selected_settings.app_name,
        version=selected_settings.api_version,
        lifespan=lifespan,
    )
    application.state.container = container
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:1420", "http://localhost:1420", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(ShotMillError)
    async def shotmill_error_handler(_: Request, exc: ShotMillError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @application.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {"name": selected_settings.app_name, "version": selected_settings.api_version}

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "shotmill-backend"}

    for router in (
        projects.router,
        project_transfer.router,
        removal.router,
        application_settings.router,
        assets.router,
        tasks.router,
        prompt_enhancements.router,
        batch_review.router,
        comfyui.router,
        generation.router,
        results.router,
        events.router,
    ):
        application.include_router(router, prefix="/api/v1")

    application.include_router(shared_media.router)
    return application


