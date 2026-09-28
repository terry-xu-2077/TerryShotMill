from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse

from shotmill.api.dependencies import ContainerDep
from shotmill.frontend_adapter.models import ApiModel

router = APIRouter(prefix="/result-archive", tags=["result-archive"])


class ArchiveFileView(ApiModel):
    role: str
    filename: str
    size: int
    url: str


class ArchivedResultView(ApiModel):
    id: str
    source_project_id: str
    source_project_title: str
    source_task_id: str
    source_task_title: str
    generated_at: datetime
    archived_at: datetime
    final_prompt: str
    params: dict[str, Any]
    files: list[ArchiveFileView]


@router.get("", response_model=list[ArchivedResultView])
def list_archived_results(
    container: ContainerDep, source_project_id: str | None = Query(None, alias="sourceProjectId"),
) -> list[ArchivedResultView]:
    return [ArchivedResultView(
        id=record.id, source_project_id=record.source_project_id,
        source_project_title=record.source_project_title,
        source_task_id=record.source_task_id, source_task_title=record.source_task_title,
        generated_at=record.generated_at, archived_at=record.archived_at,
        final_prompt=record.final_prompt, params=record.params,
        files=[ArchiveFileView(
            role=file["role"], filename=file["filename"], size=file["size"],
            url=f"/api/v1/result-archive/{record.id}/files/{index}",
        ) for index, file in enumerate(record.files)],
    ) for record in container.result_archive_service.list(source_project_id)]


@router.get("/{archive_id}/files/{index}")
def archive_file(
    archive_id: str, index: int, container: ContainerDep, download: bool = False,
) -> FileResponse:
    path, filename = container.result_archive_service.file(archive_id, index)
    return FileResponse(
        path, filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )


@router.delete("/{archive_id}", status_code=204)
def delete_archived_result(archive_id: str, container: ContainerDep) -> Response:
    container.result_archive_service.delete(archive_id)
    return Response(status_code=204)
