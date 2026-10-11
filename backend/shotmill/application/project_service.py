from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from shotmill.domain.entities import Asset, Project, Scene, TaskPlacement, new_id, utcnow
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError, ShotMillError
from shotmill.media.storage import MediaStorage
from shotmill.persistence.project_documents import ProjectDocumentStore


class ProjectService:
    def __init__(
        self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage,
        documents: ProjectDocumentStore,
    ) -> None:
        self.uow_factory = uow_factory
        self.storage = storage
        self.documents = documents

    def create_timeline(self, project_id: str, title: str) -> Scene:
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            scenes = uow.story_structure.list_scenes(project_id)
            number = max((scene.number for scene in scenes), default=0) + 1
            scene = Scene(new_id("timeline"), project_id, number,
                          title.strip() or f"时间线 {number}", "",
                          max((scene.order_key for scene in scenes), default=0) + 1)
            uow.story_structure.add_scene(scene)
            project.updated_at = utcnow()
            uow.projects.update(project)
            return scene

    def rename_timeline(self, project_id: str, timeline_id: str, title: str) -> None:
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            if not any(scene.id == timeline_id for scene in uow.story_structure.list_scenes(project_id)):
                raise NotFoundError("TIMELINE_NOT_FOUND", "Timeline not found")
            uow.story_structure.rename_scene(project_id, timeline_id, title.strip())
            project.updated_at = utcnow()
            uow.projects.update(project)

    def delete_timeline(self, project_id: str, timeline_id: str) -> None:
        with self.uow_factory() as uow:
            uow.reserve_write()
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            if not any(scene.id == timeline_id for scene in uow.story_structure.list_scenes(project_id)):
                raise NotFoundError("TIMELINE_NOT_FOUND", "Timeline not found")
            if any(item.scene_id == timeline_id for item in uow.story_structure.list_placements(project_id)):
                raise ShotMillError("TIMELINE_NOT_EMPTY", "请先移走或删除时间线中的片段", 409)
            uow.story_structure.delete_scene(project_id, timeline_id)
            project.updated_at = utcnow()
            uow.projects.update(project)

    def create(
        self,
        title: str,
        path: Path,
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
        try:
            self.documents.register_new(project.id, path)
        except (OSError, ValueError) as exc:
            raise ShotMillError("PROJECT_FILE_CREATE_FAILED", str(exc), 422) from exc
        try:
            with self.uow_factory() as uow:
                uow.projects.add(project)
        except Exception:
            self.documents.paths.pop(project.id, None)
            raise
        self.documents.remember()
        return project

    def update(
        self,
        project_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        use_description_for_ai_prompt: bool | None = None,
        cover: dict | None = None,
        director: dict | None = None,
    ) -> Project:
        with self.uow_factory() as uow:
            uow.reserve_write()
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
            if director is not None:
                project.director = dict(director)
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
                    self.storage.resolve_read(project_id, frame).read_bytes()
                ).hexdigest(),
            ))
        return identifier
