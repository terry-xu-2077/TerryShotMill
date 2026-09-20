from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from shotmill.api import (
    application_settings,
    assets,
    batch_review,
    comfyui,
    events,
    generation,
    projects,
    prompt_enhancements,
    results,
    tasks,
)
from shotmill.application.container import build_container
from shotmill.config import Settings, settings
from shotmill.domain.providers import PromptAIProvider, VideoGenerationProvider
from shotmill.errors import ShotMillError
from shotmill.persistence.migrations import upgrade_database


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
        selected_settings.projects_root.mkdir(parents=True, exist_ok=True)
        if selected_settings.auto_migrate:
            upgrade_database(selected_settings.database_url)
        await container.prompt_enhancement_queue.start()
        await container.generation_queue.start()
        try:
            yield
        finally:
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

    application.mount(
        "/media",
        StaticFiles(directory=str(selected_settings.projects_root), check_dir=False),
        name="media",
    )
    return application


app = create_app()
