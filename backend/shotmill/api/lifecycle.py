from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from shotmill.api.dependencies import ContainerDep
from shotmill.application.lifecycle_service import LifecycleAction
from shotmill.frontend_adapter.models import ApiModel

router = APIRouter(prefix="/projects", tags=["lifecycle"])


class LifecycleRequest(ApiModel):
    action: LifecycleAction


class TaskSelection(ApiModel):
    task_ids: list[str] = Field(min_length=1)


class TaskLifecycleRequest(TaskSelection):
    action: LifecycleAction


class LifecycleView(ApiModel):
    id: str
    archived_at: datetime | None
    deleted_at: datetime | None


class DeletionImpactView(ApiModel):
    source_task_id: str
    source_task_title: str
    target_task_id: str
    target_task_title: str
    kind: str
    source_result_id: str | None


class PermanentDeleteRequest(ApiModel):
    confirmed: Literal[True]
    archive_results: bool = True


class PermanentTaskDeleteRequest(PermanentDeleteRequest):
    task_ids: list[str] = Field(min_length=1)


class PermanentDeleteView(ApiModel):
    deleted_ids: list[str]
    archived_result_count: int
    cleanup_id: str


@router.post("/{project_id}/permanent-delete", response_model=PermanentDeleteView)
async def permanently_delete_project(
    project_id: str, payload: PermanentDeleteRequest, container: ContainerDep,
) -> PermanentDeleteView:
    outcome = await run_in_threadpool(
        container.permanent_delete_service.purge_project, project_id,
        archive_results=payload.archive_results,
    )
    await container.events.publish(project_id, "project.summary_changed")
    return PermanentDeleteView.model_validate(outcome)


@router.post("/{project_id}/tasks/permanent-delete", response_model=PermanentDeleteView)
async def permanently_delete_tasks(
    project_id: str, payload: PermanentTaskDeleteRequest, container: ContainerDep,
) -> PermanentDeleteView:
    outcome = await run_in_threadpool(
        container.permanent_delete_service.purge_tasks, project_id, payload.task_ids,
        archive_results=payload.archive_results,
    )
    await container.events.publish(project_id, "project.summary_changed")
    return PermanentDeleteView.model_validate(outcome)


@router.post("/{project_id}/lifecycle", response_model=LifecycleView)
async def project_lifecycle(
    project_id: str, payload: LifecycleRequest, container: ContainerDep,
) -> LifecycleView:
    project = container.lifecycle_service.transition_project(project_id, payload.action)
    await container.events.publish(project_id, "project.summary_changed")
    return LifecycleView.model_validate(project)


@router.post("/{project_id}/tasks/lifecycle", response_model=list[LifecycleView])
async def task_lifecycle(
    project_id: str, payload: TaskLifecycleRequest, container: ContainerDep,
) -> list[LifecycleView]:
    tasks = container.lifecycle_service.transition_tasks(
        project_id, payload.task_ids, payload.action,
    )
    await container.events.publish(project_id, "project.summary_changed")
    return [LifecycleView.model_validate(task) for task in tasks]


@router.post("/{project_id}/tasks/deletion-preview", response_model=list[DeletionImpactView])
def deletion_preview(
    project_id: str, payload: TaskSelection, container: ContainerDep,
) -> list[DeletionImpactView]:
    return [DeletionImpactView.model_validate(impact) for impact in
            container.lifecycle_service.deletion_impacts(project_id, payload.task_ids)]
