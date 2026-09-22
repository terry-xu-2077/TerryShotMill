from fastapi import APIRouter

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import PromptEnhancementPreviewRequest, PromptEnhancementRequest
from shotmill.application.prompt_enhancement_service import (
    EnhancementContextOptions,
    EnhancementMedia,
)
from shotmill.frontend_adapter.mapper import map_revision
from shotmill.frontend_adapter.models import (
    AiPromptRevisionView,
    PromptEnhancementPreviewView,
    PromptRevisionListResponse,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["prompt-enhancement"])


@router.post(
    "/tasks/{task_id}/prompt-enhancements",
    response_model=AiPromptRevisionView,
    status_code=201,
)
async def enhance_prompt(
    project_id: str,
    task_id: str,
    payload: PromptEnhancementRequest,
    container: ContainerDep,
) -> AiPromptRevisionView:
    revision = await container.batch_production_service.enhance_single(
        project_id,
        task_id,
        target=payload.target,
        user_prompt=payload.user_prompt,
        media=tuple(
            EnhancementMedia(asset_id=item.asset_id, reference=item.reference, role=item.role)
            for item in payload.media
        ),
        context=EnhancementContextOptions(
            include_project_background=payload.context.include_project_background,
            include_previous_task_summary=payload.context.include_previous_task_summary,
        ),
        duration_seconds=payload.generation.duration_seconds,
        mode=payload.generation.mode,
        context_mode=payload.generation.context_mode,
    )
    return map_revision(revision)


@router.post(
    "/prompt-enhancement-previews",
    response_model=PromptEnhancementPreviewView,
    status_code=200,
)
async def preview_prompt_enhancement(
    project_id: str,
    payload: PromptEnhancementPreviewRequest,
    container: ContainerDep,
) -> PromptEnhancementPreviewView:
    preview = await container.prompt_enhancement_service.preview(
        project_id,
        target=payload.target,
        user_prompt=payload.user_prompt,
        media=tuple(
            EnhancementMedia(asset_id=item.asset_id, reference=item.reference, role=item.role)
            for item in payload.media
        ),
        context=EnhancementContextOptions(
            include_project_background=payload.context.include_project_background,
            include_previous_task_summary=payload.context.include_previous_task_summary,
        ),
        duration_seconds=payload.generation.duration_seconds,
        mode=payload.generation.mode,
        context_mode=payload.generation.context_mode,
        previous_task_id=payload.previous_task_id,
    )
    return PromptEnhancementPreviewView(
        preview_id=preview.id,
        created_at=preview.created_at,
        prompt=preview.prompt,
        target_skill=preview.target_skill,
        skill_version=preview.skill_version,
        provider_id=preview.provider_id,
        model_id=preview.model_id,
    )


@router.get("/tasks/{task_id}/prompt-revisions", response_model=PromptRevisionListResponse)
def list_prompt_revisions(
    project_id: str,
    task_id: str,
    container: ContainerDep,
) -> PromptRevisionListResponse:
    revisions = container.prompt_enhancement_service.list_revisions(project_id, task_id)
    return PromptRevisionListResponse(items=[map_revision(item) for item in revisions])


@router.post(
    "/tasks/{task_id}/prompt-revisions/{revision_id}/select",
    response_model=AiPromptRevisionView,
)
def select_prompt_revision(
    project_id: str,
    task_id: str,
    revision_id: str,
    container: ContainerDep,
) -> AiPromptRevisionView:
    revision = container.prompt_enhancement_service.select_revision(
        project_id, task_id, revision_id
    )
    return map_revision(revision)
