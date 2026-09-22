from __future__ import annotations

import hashlib
from collections.abc import Callable

from shotmill.domain.entities import Asset, Project, new_id, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError, ShotMillError
from shotmill.media.storage import MediaStorage


class ProjectService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage) -> None:
        self.uow_factory = uow_factory
        self.storage = storage

    def create(
        self,
        title: str,
        description: str = "",
        use_description_for_ai_prompt: bool = False,
    ) -> Project:
        clean_title = title.strip()
        if not clean_title:
            raise ShotMillError("PROJECT_TITLE_REQUIRED", "Project title is required", 422)
        now = utcnow()
        project = Project(
            id=new_id("project"),
            title=clean_title,
            description=description.strip(),
            use_description_for_ai_prompt=use_description_for_ai_prompt,
            created_at=now,
            updated_at=now,
        )
        with self.uow_factory() as uow:
            uow.projects.add(project)
        self.storage.ensure_project_layout(project.id)
        return project

    def update(
        self,
        project_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        use_description_for_ai_prompt: bool | None = None,
        cover: dict | None = None,
    ) -> Project:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            if title is not None:
                clean_title = title.strip()
                if not clean_title:
                    raise ShotMillError("PROJECT_TITLE_REQUIRED", "Project title is required", 422)
                project.title = clean_title
            if description is not None:
                project.description = description.strip()
            if use_description_for_ai_prompt is not None:
                project.use_description_for_ai_prompt = use_description_for_ai_prompt
            if cover is not None:
                project.cover_asset_id = self._select_cover(uow, project_id, cover)
            project.updated_at = utcnow()
            uow.projects.update(project)
            return project

    def _select_cover(self, uow: UnitOfWork, project_id: str, cover: dict) -> str | None:
        if cover["kind"] == "auto":
            return None
        asset = uow.assets.get(cover["asset_id"]) if cover.get("asset_id") else None
        if cover.get("asset_id") and (asset is None or asset.project_id != project_id):
            raise NotFoundError("ASSET_NOT_FOUND", "封面资产不存在。")
        if cover["kind"] == "asset":
            if asset is None or asset.media_type != "image":
                raise ShotMillError("COVER_IMAGE_REQUIRED", "请选择图片资产。", 422)
            return asset.id
        if asset is not None:
            if asset.media_type != "video":
                raise ShotMillError("COVER_VIDEO_REQUIRED", "请选择视频。", 422)
            relative = asset.project_relative_path
        else:
            result = uow.results.get(cover.get("result_id", ""))
            if result is None or result.project_id != project_id:
                raise NotFoundError("RESULT_NOT_FOUND", "视频结果不存在。")
            prefix = f"/media/{project_id}/"
            if not result.video_url.startswith(prefix):
                raise ShotMillError("COVER_VIDEO_REQUIRED", "请选择已保存的项目视频。", 422)
            relative = result.video_url[len(prefix):]
        frame = self.storage.video_thumbnail(project_id, relative, seconds=cover.get("seconds", 0))
        # Stable identity makes a retried save reuse the same derived frame.
        identifier = "cover-" + hashlib.sha256(f"{project_id}/{frame}".encode()).hexdigest()[:24]
        if uow.assets.get(identifier) is None:
            uow.assets.add(Asset(
                id=identifier, project_id=project_id, name="项目封面",
                original_filename="video-frame.png", project_relative_path=frame,
                media_type="image", category="reference",
                hash=hashlib.sha256(
                    self.storage.resolve(project_id, frame).read_bytes()
                ).hexdigest(),
            ))
        return identifier
