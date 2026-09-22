from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import ProjectCreateRequest, ProjectPatchRequest
from shotmill.application.runtime_control import RuntimeControlService
from shotmill.frontend_adapter.models import (
    ProjectListResponse,
    ProjectRuntimeView,
    ProjectSettingsView,
    ProjectSummary,
    ProjectWorkspaceView,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
def list_projects(container: ContainerDep) -> ProjectListResponse:
    return ProjectListResponse(items=container.workspace_query.list_projects())


@router.get("/runtime", response_model=list[ProjectRuntimeView])
def global_runtime(container: ContainerDep) -> list[ProjectRuntimeView]:
    return container.workspace_query.global_runtime()


@router.post("", response_model=ProjectSummary, status_code=201)
def create_project(
    payload: ProjectCreateRequest,
    container: ContainerDep,
) -> ProjectSummary:
    project = container.project_service.create(
        payload.title,
        payload.description,
        payload.use_description_for_ai_prompt,
    )
    return container.workspace_query.project_summary(project.id)


@router.patch("/{project_id}", response_model=ProjectSummary)
def update_project(
    project_id: str,
    payload: ProjectPatchRequest,
    container: ContainerDep,
) -> ProjectSummary:
    container.project_service.update(
        project_id,
        title=payload.title,
        description=payload.description,
        use_description_for_ai_prompt=payload.use_description_for_ai_prompt,
        cover=payload.cover.model_dump() if payload.cover is not None else None,
    )
    return container.workspace_query.project_summary(project_id)


@router.get("/{project_id}/settings", response_model=ProjectSettingsView)
def get_project_settings(
    project_id: str,
    container: ContainerDep,
) -> ProjectSettingsView:
    return container.workspace_query.project_settings(project_id)


@router.get("/{project_id}/workspace", response_model=ProjectWorkspaceView)
def get_project_workspace(
    project_id: str,
    container: ContainerDep,
) -> ProjectWorkspaceView:
    return container.workspace_query.workspace(project_id)


class RuntimeActionRequest(BaseModel):
    action: Literal["up", "down", "pause", "resume", "remove"]


@router.post("/{project_id}/runtime/{kind}/{job_id}")
async def runtime_action(project_id: str, kind: Literal["prompt", "video"], job_id: str,
                         payload: RuntimeActionRequest, container: ContainerDep):
    service = RuntimeControlService(
        container.generation_service, container.batch_production_service
    )
    await service.act(project_id, kind, job_id, payload.action)
    return {"ok": True}
