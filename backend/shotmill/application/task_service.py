from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from shotmill.application.context_duration import previous_video_duration
from shotmill.domain.entities import ContextLink, Task, TaskAssetBinding, new_id, utcnow
from shotmill.domain.enums import PromptSource, TaskState
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError, ShotMillError
from shotmill.media.storage import MediaStorage


@dataclass(frozen=True, slots=True)
class SaveTaskAsset:
    asset_id: str
    reference: str
    role: str | None = None


@dataclass(frozen=True, slots=True)
class SaveTaskData:
    title: str
    summary: str = ""
    script_source: str = ""
    user_intent: str = ""
    user_prompt: str = ""
    ai_prompt: str = ""
    prompt_source: str = "user"
    duration_seconds: float = 6.0
    generation: dict | None = None
    asset_bindings: tuple[SaveTaskAsset, ...] = ()
    user_view_mode: str = "visual"
    ai_view_mode: str = "visual"
    revision: int | None = None


class TaskService:
    def __init__(
        self, uow_factory: Callable[[], UnitOfWork], storage: MediaStorage | None = None
    ) -> None:
        self.uow_factory = uow_factory
        self.storage = storage

    def _validate_assets(
        self,
        uow: UnitOfWork,
        project_id: str,
        values: tuple[SaveTaskAsset, ...],
    ) -> list[TaskAssetBinding]:
        bindings: list[TaskAssetBinding] = []
        for index, item in enumerate(values):
            asset = uow.assets.get(item.asset_id)
            if asset is None or asset.project_id != project_id:
                raise NotFoundError("ASSET_NOT_FOUND", f"Asset not found: {item.asset_id}")
            reference = item.reference.strip()
            if not reference:
                raise ShotMillError(
                    "ASSET_REFERENCE_REQUIRED",
                    "Asset reference label is required",
                    422,
                )
            bindings.append(
                TaskAssetBinding(
                    asset_id=item.asset_id,
                    reference=reference,
                    role=item.role.strip() if item.role else None,
                    order_index=index,
                )
            )
        return bindings

    @staticmethod
    def _normalize_generation(generation: dict | None, previous_duration: float | None) -> dict:
        value = dict(generation or {})
        context_mode = str(value.get("contextMode", value.get("context_mode", "尾帧承接")))
        start = value.get("contextStartSeconds", value.get("context_start_seconds"))
        end = value.get("contextEndSeconds", value.get("context_end_seconds"))
        duration = value.get("contextDurationSeconds", value.get("context_duration_seconds"))
        if context_mode == "片段承接":
            if previous_duration is None:
                raise ShotMillError(
                    "PREVIOUS_TASK_REQUIRED",
                    "Segment continuation requires a previous task",
                    422,
                )
            if start is None or end is None:
                if duration is not None:
                    end = previous_duration
                    start = max(0.0, end - float(duration))
                else:
                    end = previous_duration
                    start = max(0.0, end - 1.0)
            start = float(start)
            end = float(end)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0
                or end <= start
                or end > previous_duration + 1e-9
            ):
                raise ShotMillError(
                    "INVALID_CONTEXT_RANGE",
                    "Continuation range is outside the previous task duration",
                    422,
                )
            duration = end - start
        else:
            start = None
            end = None
            duration = None
        return {
            "resolution": str(value.get("resolution", "1080p")),
            "quality": str(value.get("quality", "标准")),
            "mode": str(value.get("mode", "全能参考")),
            "contextMode": context_mode,
            "contextStartSeconds": start,
            "contextEndSeconds": end,
            "contextDurationSeconds": duration,
            **{
                key: item
                for key, item in value.items()
                if key
                not in {
                    "resolution",
                    "quality",
                    "mode",
                    "contextMode",
                    "context_mode",
                    "contextStartSeconds",
                    "context_start_seconds",
                    "contextEndSeconds",
                    "context_end_seconds",
                    "contextDurationSeconds",
                    "context_duration_seconds",
                }
            },
        }

    @staticmethod
    def _previous_task(tasks: list[Task], display_order: int) -> Task | None:
        return next((item for item in reversed(tasks) if item.display_order < display_order), None)

    def _replace_context(self, uow: UnitOfWork, task: Task, previous: Task | None) -> None:
        mode = task.generation_params.get("contextMode", "不承接")
        if mode == "不承接" or previous is None:
            uow.contexts.replace_for_target(task.id, [])
            return
        kind = "visual" if mode in {"片段承接", "尾帧承接"} else "semantic"
        uow.contexts.replace_for_target(
            task.id,
            [
                ContextLink(
                    id=new_id("context"),
                    project_id=task.project_id,
                    source_task_id=previous.id,
                    target_task_id=task.id,
                    kind=kind,
                    source_result_id=previous.primary_result_id,
                    stale=False,
                )
            ],
        )

    def create(self, project_id: str, data: SaveTaskData) -> Task:
        with self.uow_factory() as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            tasks = uow.tasks.list_by_project(project_id)
            order = uow.tasks.next_display_order(project_id)
            previous = self._previous_task(tasks, order)
            generation = self._normalize_generation(
                data.generation,
                previous_video_duration(uow, previous, self.storage),
            )
            bindings = self._validate_assets(uow, project_id, data.asset_bindings)
            source = PromptSource(data.prompt_source)
            now = utcnow()
            task = Task(
                id=new_id("task"),
                project_id=project_id,
                display_order=order,
                title=data.title.strip() or f"任务 {order}",
                summary=data.summary.strip(),
                script_source=data.script_source,
                user_intent=data.user_intent,
                user_prompt=data.user_prompt,
                ai_prompt=data.ai_prompt,
                prompt_source=source,
                generation_params=generation,
                planned_duration_seconds=max(0.1, float(data.duration_seconds)),
                user_view_mode=(
                    data.user_view_mode if data.user_view_mode in {"visual", "text"} else "visual"
                ),
                ai_view_mode=(
                    data.ai_view_mode if data.ai_view_mode in {"visual", "text"} else "visual"
                ),
                asset_bindings=bindings,
                created_at=now,
                updated_at=now,
            )
            task.select_final_prompt()
            task.state = TaskState.READY if task.final_prompt.strip() else TaskState.DRAFT
            uow.tasks.add(task)
            self._replace_context(uow, task, previous)
            project.updated_at = now
            uow.projects.update(project)
            return task

    def update_editor_preference(
        self, project_id: str, task_id: str, *,
        user_view_mode: str | None = None, ai_view_mode: str | None = None,
    ) -> dict[str, str]:
        # Presentation preferences must not save drafts or change production/review state.
        values = {key: value for key, value in {
            "user_view_mode": user_view_mode, "ai_view_mode": ai_view_mode,
        }.items() if value is not None}
        if any(value not in {"visual", "text"} for value in values.values()):
            raise ShotMillError("INVALID_VIEW_MODE", "Invalid prompt view mode", 422)
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            uow.tasks.update_editor_preference(task_id, values)
            return {
                "user_view_mode": values.get("user_view_mode", task.user_view_mode),
                "ai_view_mode": values.get("ai_view_mode", task.ai_view_mode),
            }

    def update(self, project_id: str, task_id: str, data: SaveTaskData) -> Task:
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            if task.state in {TaskState.QUEUED, TaskState.RUNNING}:
                raise ConflictError("TASK_BUSY", "Running or queued task cannot be edited")
            if data.revision is not None and data.revision != task.revision:
                raise ConflictError(
                    "TASK_CONFLICT",
                    "Task was modified after the editor was loaded",
                    {"revision": task.revision},
                )
            tasks = uow.tasks.list_by_project(project_id)
            previous = self._previous_task(tasks, task.display_order)
            old_final = task.final_prompt
            old_prompt_source = task.prompt_source
            task.title = data.title.strip() or task.title
            task.summary = data.summary.strip()
            task.script_source = data.script_source
            task.user_intent = data.user_intent
            task.user_prompt = data.user_prompt
            task.ai_prompt = data.ai_prompt
            task.prompt_source = PromptSource(data.prompt_source)
            task.planned_duration_seconds = max(0.1, float(data.duration_seconds))
            task.generation_params = self._normalize_generation(
                data.generation,
                previous_video_duration(uow, previous, self.storage),
            )
            task.asset_bindings = self._validate_assets(uow, project_id, data.asset_bindings)
            task.user_view_mode = (
                data.user_view_mode if data.user_view_mode in {"visual", "text"} else "visual"
            )
            task.ai_view_mode = (
                data.ai_view_mode if data.ai_view_mode in {"visual", "text"} else "visual"
            )
            task.select_final_prompt()
            if old_prompt_source != task.prompt_source or old_final != task.final_prompt:
                task.approved_prompt_source = None
                task.approved_prompt_hash = None
                task.approved_at = None
                task.approved_revision_id = None
            task.revision += 1
            task.updated_at = utcnow()
            task.state = TaskState.READY if task.final_prompt.strip() else TaskState.DRAFT
            task.progress = None
            uow.tasks.update(task)
            self._replace_context(uow, task, previous)
            if old_final != task.final_prompt:
                uow.contexts.mark_stale_by_source(task.id)
            project = uow.projects.get(project_id)
            if project is not None:
                project.updated_at = task.updated_at
                uow.projects.update(project)
            return task

    def reorder(self, project_id: str, task_ids: list[str]) -> None:
        with self.uow_factory() as uow:
            current = uow.tasks.list_by_project(project_id)
            if {item.id for item in current} != set(task_ids) or len(current) != len(task_ids):
                raise ShotMillError(
                    "INVALID_TASK_ORDER",
                    "Task order must contain every project task exactly once",
                    422,
                )
            uow.tasks.reorder(project_id, task_ids)
            project = uow.projects.get(project_id)
            if project is not None:
                project.updated_at = utcnow()
                uow.projects.update(project)
