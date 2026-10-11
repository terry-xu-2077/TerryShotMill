from typing import Literal
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from shotmill.api.dependencies import ContainerDep
from shotmill.errors import ShotMillError
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
        Path(payload.path),
        payload.description,
        payload.use_description_for_ai_prompt,
    )
    return container.workspace_query.project_summary(project.id)


class ProjectOpenRequest(BaseModel):
    path: str


class TimelineRequest(BaseModel):
    title: str


@router.post("/open", response_model=ProjectSummary)
def open_project(payload: ProjectOpenRequest, container: ContainerDep) -> ProjectSummary:
    try:
        project_id = container.project_documents.open(Path(payload.path))
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, SQLAlchemyError) as exc:
        raise ShotMillError("PROJECT_FILE_OPEN_FAILED", "工程文件无法打开", 422) from exc
    return container.workspace_query.project_summary(project_id)


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
        director=payload.director,
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


@router.post("/{project_id}/timelines", status_code=201)
def create_timeline(project_id: str, payload: TimelineRequest, container: ContainerDep) -> dict:
    scene = container.project_service.create_timeline(project_id, payload.title)
    return {"id": scene.id, "title": scene.title, "taskIds": []}


@router.patch("/{project_id}/timelines/{timeline_id}")
def rename_timeline(project_id: str, timeline_id: str, payload: TimelineRequest,
                    container: ContainerDep) -> dict:
    container.project_service.rename_timeline(project_id, timeline_id, payload.title)
    return {"id": timeline_id, "title": payload.title.strip()}


@router.delete("/{project_id}/timelines/{timeline_id}", status_code=204)
def delete_timeline(project_id: str, timeline_id: str, container: ContainerDep) -> None:
    container.project_service.delete_timeline(project_id, timeline_id)


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
