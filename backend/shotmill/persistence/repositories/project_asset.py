from __future__ import annotations

from copy import deepcopy

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from shotmill.domain.entities import Asset, Project
from shotmill.persistence import models
from shotmill.persistence.repositories.mappers import asset_from_model, project_from_model


class SqlAlchemyProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_transfer_requirements(self, project_id: str) -> list[dict]:
        row = self.session.get(models.ProjectModel, project_id)
        if row is None:
            raise KeyError(project_id)
        return deepcopy(row.transfer_requirements)

    def set_transfer_requirements(self, project_id: str, requirements: list[dict]) -> None:
        row = self.session.get(models.ProjectModel, project_id)
        if row is None:
            raise KeyError(project_id)
        row.transfer_requirements = deepcopy(requirements)
        self.session.flush()

    def list(self) -> list[Project]:
        rows = self.session.scalars(
            select(models.ProjectModel).order_by(models.ProjectModel.updated_at.desc())
        ).all()
        return [project_from_model(row) for row in rows]

    def get(self, project_id: str) -> Project | None:
        row = self.session.get(models.ProjectModel, project_id)
        return project_from_model(row) if row else None

    def delete(self, project_id: str) -> None:
        self.session.execute(
            delete(models.ProjectModel).where(models.ProjectModel.id == project_id)
        )
        self.session.flush()

    def add(self, project: Project) -> Project:
        self.session.add(
            models.ProjectModel(
                id=project.id,
                title=project.title,
                description=project.description,
                use_description_for_ai_prompt=project.use_description_for_ai_prompt,
                cover_asset_id=project.cover_asset_id,
                archived_at=project.archived_at,
                deleted_at=project.deleted_at,
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
        )
        self.session.flush()
        return project

    def update(self, project: Project) -> Project:
        row = self.session.get(models.ProjectModel, project.id)
        if row is None:
            raise KeyError(project.id)
        row.title = project.title
        row.description = project.description
        row.use_description_for_ai_prompt = project.use_description_for_ai_prompt
        row.cover_asset_id = project.cover_asset_id
        row.archived_at = project.archived_at
        row.deleted_at = project.deleted_at
        row.updated_at = project.updated_at
        self.session.flush()
        return project


class SqlAlchemyAssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_project(self, project_id: str) -> list[Asset]:
        rows = self.session.scalars(
            select(models.AssetModel)
            .where(models.AssetModel.project_id == project_id)
            .order_by(models.AssetModel.created_at)
        ).all()
        return [asset_from_model(row) for row in rows]

    def get(self, asset_id: str) -> Asset | None:
        row = self.session.get(models.AssetModel, asset_id)
        return asset_from_model(row) if row else None

    def add(self, asset: Asset) -> Asset:
        self.session.add(
            models.AssetModel(
                id=asset.id,
                project_id=asset.project_id,
                name=asset.name,
                original_filename=asset.original_filename,
                project_relative_path=asset.project_relative_path,
                media_type=asset.media_type,
                category=asset.category,
                tags=asset.tags,
                width=asset.width,
                height=asset.height,
                duration=asset.duration,
                hash=asset.hash,
                thumbnail_path=asset.thumbnail_path,
                provenance=asset.provenance,
                created_at=asset.created_at,
                updated_at=asset.updated_at,
            )
        )
        self.session.flush()
        return asset

    def update(self, asset: Asset) -> Asset:
        row = self.session.get(models.AssetModel, asset.id)
        if row is None:
            raise KeyError(asset.id)
        row.name = asset.name
        row.category = asset.category
        row.tags = asset.tags
        row.width = asset.width
        row.height = asset.height
        row.duration = asset.duration
        row.thumbnail_path = asset.thumbnail_path
        row.updated_at = asset.updated_at
        self.session.flush()
        return asset

    def delete(self, asset_id: str) -> None:
        self.session.execute(delete(models.AssetModel).where(models.AssetModel.id == asset_id))
        self.session.flush()

    def count_by_project(self, project_id: str) -> int:
        value = self.session.scalar(
            select(func.count())
            .select_from(models.AssetModel)
            .where(models.AssetModel.project_id == project_id)
        )
        return int(value or 0)

    def binding_count(self, asset_id: str) -> int:
        value = self.session.scalar(
            select(func.count())
            .select_from(models.TaskAssetBindingModel)
            .where(models.TaskAssetBindingModel.asset_id == asset_id)
        )
        return int(value or 0)
