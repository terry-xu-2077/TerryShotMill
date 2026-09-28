from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from pydantic import Field

from shotmill.api.dependencies import ContainerDep
from shotmill.api.schemas import AssetPatchRequest
from shotmill.application.asset_import_service import ImportSelection
from shotmill.frontend_adapter.mapper import map_asset
from shotmill.frontend_adapter.models import ApiModel, AssetListResponse, ProjectAssetView

router = APIRouter(prefix="/projects/{project_id}/assets", tags=["assets"])


class ImportSourceRequest(ApiModel):
    kind: Literal["asset", "result", "archive"]
    id: str = Field(min_length=1)


class ImportSourcesRequest(ApiModel):
    sources: list[ImportSourceRequest] = Field(min_length=1)


class ImportCandidateView(ApiModel):
    kind: Literal["asset", "result", "archive"]
    id: str
    name: str
    source_project_id: str
    source_project_title: str
    media_type: str
    preview_url: str | None
    created_at: datetime


@router.get("/import-sources", response_model=list[ImportCandidateView])
def import_candidates(
    project_id: str, container: ContainerDep,
    source_project_id: str | None = Query(None, alias="sourceProjectId"),
) -> list[ImportCandidateView]:
    return [ImportCandidateView.model_validate(item) for item in
            container.asset_import_service.candidates(project_id, source_project_id)]


@router.post("/import", response_model=list[ProjectAssetView], status_code=201)
def import_sources(
    project_id: str, payload: ImportSourcesRequest, container: ContainerDep,
) -> list[ProjectAssetView]:
    assets = container.asset_import_service.import_sources(
        project_id, [ImportSelection(item.kind, item.id) for item in payload.sources],
    )
    return [map_asset(asset, container.storage) for asset in assets]


def _parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [part.strip() for part in value.split(",")]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


@router.get("", response_model=AssetListResponse)
def list_assets(
    project_id: str,
    container: ContainerDep,
    purpose: Annotated[str | None, Query()] = None,
) -> AssetListResponse:
    return AssetListResponse(items=container.workspace_query.list_assets(project_id, purpose))


@router.post("", response_model=ProjectAssetView, status_code=201)
async def import_asset(
    project_id: str,
    file: Annotated[UploadFile, File()],
    container: ContainerDep,
    name: Annotated[str | None, Form()] = None,
    category: Annotated[str, Form()] = "reference",
    tags: Annotated[str | None, Form()] = None,
) -> ProjectAssetView:
    content = await file.read()
    asset = container.asset_service.import_bytes(
        project_id,
        file.filename or "asset.bin",
        content,
        content_type=file.content_type,
        name=name,
        category=category,
        tags=_parse_tags(tags),
    )
    return map_asset(asset, container.storage)


@router.patch("/{asset_id}", response_model=ProjectAssetView)
def update_asset(
    project_id: str,
    asset_id: str,
    payload: AssetPatchRequest,
    container: ContainerDep,
) -> ProjectAssetView:
    asset = container.asset_service.update(
        project_id,
        asset_id,
        name=payload.name,
        category=payload.category,
        tags=payload.tags,
    )
    return map_asset(asset, container.storage)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    project_id: str,
    asset_id: str,
    container: ContainerDep,
) -> Response:
    container.asset_service.delete(project_id, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
