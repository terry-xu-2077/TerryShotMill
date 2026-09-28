from fastapi import APIRouter
from fastapi.responses import FileResponse

from shotmill.api.dependencies import ContainerDep

router = APIRouter()


@router.api_route(
    "/media/{project_id}/shared/{owner_kind}/{owner_id}/{slot}",
    methods=["GET", "HEAD"], include_in_schema=False,
)
def shared_media(
    project_id: str, owner_kind: str, owner_id: str, slot: str, container: ContainerDep,
) -> FileResponse:
    media = container.project_file_reader.read(
        project_id, f"shared/{owner_kind}/{owner_id}/{slot}",
    )
    return FileResponse(
        media.path, media_type=media.mime_type, filename=media.filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


@router.api_route(
    "/media/{project_id}/{relative:path}",
    methods=["GET", "HEAD"], include_in_schema=False,
)
def legacy_media(project_id: str, relative: str, container: ContainerDep) -> FileResponse:
    media = container.project_file_reader.read(project_id, relative)
    return FileResponse(
        media.path, media_type=media.mime_type, filename=media.filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )
