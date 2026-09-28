from contextlib import ExitStack
from dataclasses import asdict
from typing import Annotated
from zipfile import BadZipFile

from anyio import CancelScope
from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from shotmill.api.dependencies import ContainerDep
from shotmill.errors import ShotMillError
from shotmill.frontend_adapter.models import ApiModel
from shotmill.media.project_package import DEFAULT_LIMITS

router = APIRouter(prefix="/projects", tags=["project-transfer"])


class ProjectImportResponse(ApiModel):
    project_id: str
    provider_requirements: list[dict]


class ProjectExportResponse(ApiModel):
    token: str
    expires_in_seconds: int


class PendingConfigurationView(ApiModel):
    task_id: str
    title: str
    revision: int
    source_configuration_id: str | None
    read_only: bool


class ConfirmConfigurationRequest(ApiModel):
    configuration_id: str = Field(min_length=1, max_length=240)
    revision: int = Field(ge=0)


@router.get("/{project_id}/import-configuration", response_model=list[PendingConfigurationView])
def pending_import_configuration(project_id: str, container: ContainerDep):
    return [PendingConfigurationView(**asdict(item))
            for item in container.imported_generation_configuration.pending(project_id)]


@router.post("/{project_id}/import-configuration/{task_id}/confirm", status_code=204)
async def confirm_import_configuration(
    project_id: str, task_id: str, payload: ConfirmConfigurationRequest, container: ContainerDep,
):
    container.imported_generation_configuration.confirm(
        project_id, task_id, payload.configuration_id, payload.revision,
    )
    await container.events.publish(project_id, "project.summary_changed")


class _ExportResponse(FileResponse):
    def __init__(self, path, lifetime: ExitStack):
        super().__init__(path, media_type="application/zip", filename="shotmill-project.zip",
                         headers={"Cache-Control": "no-store"})
        self.lifetime = lifetime

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await run_in_threadpool(self.lifetime.close)


@router.get("/{project_id}/export", response_class=FileResponse,
            responses={200: {"content": {"application/zip": {"schema": {
                "type": "string", "format": "binary",
            }}}}})
def export_project(project_id: str, container: ContainerDep):
    lifetime = ExitStack()
    try:
        path = lifetime.enter_context(container.project_export_service.prepare(project_id))
        return _ExportResponse(path, lifetime)
    except BaseException:
        lifetime.close()
        raise


@router.post("/{project_id}/exports", response_model=ProjectExportResponse, status_code=201)
def prepare_export(project_id: str, container: ContainerDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        token = container.project_export_downloads.prepare(project_id)
    except OSError as exc:
        raise ShotMillError(
            "PROJECT_EXPORT_STORAGE_ERROR", "项目包写入失败，请检查磁盘空间和文件访问权限。", 500,
        ) from exc
    except ValueError as exc:
        raise ShotMillError(
            "PROJECT_EXPORT_INVALID", "项目媒体路径或容量不符合导出要求。", 422,
        ) from exc
    return ProjectExportResponse(
        token=token, expires_in_seconds=container.project_export_downloads.ttl_seconds,
    )


@router.get("/exports/{token}", response_class=FileResponse)
def download_prepared_export(token: str, container: ContainerDep):
    path, lifetime = container.project_export_downloads.claim(token)
    try:
        return _ExportResponse(path, lifetime)
    except BaseException:
        lifetime.close()
        raise


@router.delete("/exports/{token}", status_code=204)
def discard_prepared_export(token: str, container: ContainerDep):
    container.project_export_downloads.discard(token)


@router.post("/import", response_model=ProjectImportResponse, status_code=201)
def import_project(container: ContainerDep, file: Annotated[UploadFile, File()]):
    if file.size is not None and file.size > (
        DEFAULT_LIMITS.max_total_bytes + DEFAULT_LIMITS.max_manifest_bytes + 16 * 1024**2
    ):
        raise ShotMillError("PROJECT_PACKAGE_TOO_LARGE", "项目包超过大小限制。", 413)
    try:
        outcome = container.project_import_service.import_package(file.file)
    except (BadZipFile, ValueError) as exc:
        raise ShotMillError("PROJECT_PACKAGE_INVALID", "项目包损坏或格式不受支持。", 422) from exc
    return ProjectImportResponse(
        project_id=outcome.project_id, provider_requirements=outcome.provider_requirements,
    )
