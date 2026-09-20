from __future__ import annotations

from fastapi import APIRouter, status

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import BatchPromptEnhancementRequest, VideoBatchRequest
from shotmill.frontend_adapter.models import (
    BatchPromptEnhancementItemView,
    BatchPromptEnhancementResponse,
    PromptReviewItemView,
    PromptReviewStateView,
    VideoBatchEligibilityView,
    VideoBatchResponse,
    VideoBatchSkippedItem,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["batch-review"])


def _review_item(item) -> PromptReviewItemView:
    return PromptReviewItemView(
        task_id=item.task_id,
        prompt_review_status=item.prompt_review_status,
        approved_revision=item.approved_revision,
        approved_at=item.approved_at,
    )


@router.get("/prompt-review-state", response_model=PromptReviewStateView)
def get_prompt_review_state(project_id: str, container: ContainerDep) -> PromptReviewStateView:
    items = container.prompt_review_service.list_state(project_id)
    return PromptReviewStateView(items=[_review_item(item) for item in items])


@router.post("/tasks/{task_id}/prompt-review", response_model=PromptReviewItemView)
@router.post("/tasks/{task_id}/prompt-review/approve", response_model=PromptReviewItemView)
def approve_prompt(
    project_id: str,
    task_id: str,
    container: ContainerDep,
) -> PromptReviewItemView:
    return _review_item(container.prompt_review_service.approve(project_id, task_id))


@router.post(
    "/prompt-enhancement-batches",
    response_model=BatchPromptEnhancementResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_prompt_enhancement_batch(
    project_id: str,
    payload: BatchPromptEnhancementRequest,
    container: ContainerDep,
) -> BatchPromptEnhancementResponse:
    result = await container.batch_production_service.create_prompt_batch(
        project_id,
        task_ids=payload.task_ids,
        include_project_background=payload.include_project_background,
        include_previous_task_summary=payload.include_previous_task_summary,
    )
    return BatchPromptEnhancementResponse(
        batch_id=result.batch_id,
        state=result.state,
        items=[
            BatchPromptEnhancementItemView(
                task_id=item.task_id,
                state=item.state,
                revision_id=item.revision_id,
                error=item.error,
            )
            for item in result.items
        ],
    )


@router.get(
    "/prompt-enhancement-batches/{batch_id}",
    response_model=BatchPromptEnhancementResponse,
)
def get_prompt_enhancement_batch(
    project_id: str,
    batch_id: str,
    container: ContainerDep,
) -> BatchPromptEnhancementResponse:
    result = container.batch_production_service.prompt_batch_result(project_id, batch_id)
    return BatchPromptEnhancementResponse(
        batch_id=result.batch_id,
        state=result.state,
        items=[
            BatchPromptEnhancementItemView(
                task_id=item.task_id,
                state=item.state,
                revision_id=item.revision_id,
                error=item.error,
            )
            for item in result.items
        ],
    )


def _video_eligibility_response(eligibility) -> VideoBatchEligibilityView:
    return VideoBatchEligibilityView(
        eligible_task_ids=eligibility.eligible_task_ids,
        skipped=[
            VideoBatchSkippedItem(task_id=item.task_id, reason=item.reason)
            for item in eligibility.skipped
        ],
    )


@router.post(
    "/video-generation-batches/eligibility",
    response_model=VideoBatchEligibilityView,
)
def check_video_batch_eligibility(
    project_id: str,
    payload: VideoBatchRequest,
    container: ContainerDep,
) -> VideoBatchEligibilityView:
    return _video_eligibility_response(
        container.batch_production_service.video_batch_eligibility(
            project_id,
            payload.task_ids,
        )
    )


@router.post(
    "/video-generation-batches",
    response_model=VideoBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_video_generation_batch(
    project_id: str,
    payload: VideoBatchRequest,
    container: ContainerDep,
) -> VideoBatchResponse:
    result = await container.batch_production_service.create_video_batch(
        project_id,
        payload.task_ids,
    )
    return VideoBatchResponse(
        batch_id=result.batch_id,
        eligible_task_ids=result.eligible_task_ids,
        skipped=[
            VideoBatchSkippedItem(task_id=item.task_id, reason=item.reason)
            for item in result.skipped
        ],
    )
