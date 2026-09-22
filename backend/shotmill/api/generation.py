from fastapi import APIRouter

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import CancelVideoJobsRequest, GenerationSubmitRequest
from shotmill.frontend_adapter.mapper import map_job
from shotmill.frontend_adapter.models import CancelledVideoJobsView, JobView

router = APIRouter(tags=["generation"])


@router.post(
    "/projects/{project_id}/video-generation-queue/cancel",
    response_model=CancelledVideoJobsView,
)
async def cancel_queued_videos(
    project_id: str, payload: CancelVideoJobsRequest, container: ContainerDep,
) -> CancelledVideoJobsView:
    return CancelledVideoJobsView(
        cancelled_job_ids=await container.generation_service.cancel_queued(
            project_id, payload.job_ids,
        ),
    )


@router.post(
    "/projects/{project_id}/tasks/{task_id}/generation",
    response_model=JobView,
    status_code=202,
)
async def submit_generation(
    project_id: str,
    task_id: str,
    payload: GenerationSubmitRequest,
    container: ContainerDep,
) -> JobView:
    job = await container.generation_service.submit(project_id, task_id, seed=payload.seed)
    return map_job(job)


@router.get("/jobs/{job_id}", response_model=JobView)
def get_job(
    job_id: str,
    container: ContainerDep,
) -> JobView:
    return map_job(container.generation_service.get_job(job_id))
