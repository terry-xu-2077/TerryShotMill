from fastapi import APIRouter
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from shotmill.api.dependencies import ContainerDep
from shotmill.frontend_adapter.models import ApiModel

router = APIRouter(prefix="/projects", tags=["removal"])


class TaskSelection(ApiModel):
    task_ids: list[str] = Field(min_length=1)


class DeletionImpactView(ApiModel):
    source_task_id: str
    source_task_title: str
    target_task_id: str
    target_task_title: str
    kind: str
    source_result_id: str | None


@router.delete("/{project_id}", status_code=204)
async def remove_project(project_id: str, container: ContainerDep) -> None:
    await run_in_threadpool(container.removal_service.remove_project, project_id)
    await container.events.publish(project_id, "project.summary_changed")


@router.post("/{project_id}/tasks/delete")
async def delete_tasks(project_id: str, payload: TaskSelection,
                       container: ContainerDep) -> dict[str, list[str]]:
    ids = await run_in_threadpool(
        container.removal_service.delete_tasks, project_id, payload.task_ids,
    )
    await container.events.publish(project_id, "project.summary_changed")
    return {"deletedIds": ids}


@router.post("/{project_id}/tasks/deletion-preview", response_model=list[DeletionImpactView])
def deletion_preview(project_id: str, payload: TaskSelection,
                     container: ContainerDep) -> list[DeletionImpactView]:
    return [DeletionImpactView.model_validate(item) for item in
            container.removal_service.deletion_impacts(project_id, payload.task_ids)]
