from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from shotmill.domain.entities import Task, TaskAssetBinding
from shotmill.persistence import models
from shotmill.persistence.repositories.mappers import task_from_model


class SqlAlchemyTaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_by_project(self, project_id: str) -> list[Task]:
        rows = self.session.scalars(
            select(models.TaskModel)
            .where(models.TaskModel.project_id == project_id)
            .order_by(models.TaskModel.display_order)
        ).all()
        return [task_from_model(self.session, row) for row in rows]

    def get(self, task_id: str) -> Task | None:
        row = self.session.get(models.TaskModel, task_id)
        return task_from_model(self.session, row) if row else None

    def add(self, task: Task) -> Task:
        self.session.add(
            models.TaskModel(
                id=task.id,
                project_id=task.project_id,
                display_order=task.display_order,
                title=task.title,
                summary=task.summary,
                script_source=task.script_source,
                user_intent=task.user_intent,
                user_prompt=task.user_prompt,
                ai_prompt=task.ai_prompt,
                final_prompt=task.final_prompt,
                prompt_source=task.prompt_source.value,
                generation_params=task.generation_params,
                planned_duration_seconds=task.planned_duration_seconds,
                state=task.state.value,
                progress=task.progress,
                primary_result_id=task.primary_result_id,
                revision=task.revision,
                approved_prompt_source=(
                    task.approved_prompt_source.value if task.approved_prompt_source else None
                ),
                approved_prompt_hash=task.approved_prompt_hash,
                approved_at=task.approved_at,
                approved_revision_id=task.approved_revision_id,
                user_view_mode=task.user_view_mode,
                ai_view_mode=task.ai_view_mode,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
        )
        self.session.flush()
        scene = self.session.scalar(
            select(models.SceneModel)
            .where(models.SceneModel.project_id == task.project_id)
            .order_by(models.SceneModel.order_key)
            .limit(1)
        )
        if scene is None:
            scene = models.SceneModel(
                id=f"scene-{task.project_id}",
                project_id=task.project_id,
                number=1,
                title="",
                summary="",
                order_key=1,
            )
            self.session.add(scene)
            self.session.flush()
        self.session.add(
            models.TaskPlacementModel(
                task_id=task.id,
                scene_id=scene.id,
                order_key=task.display_order,
            )
        )
        self.replace_bindings(task.id, task.asset_bindings)
        return task

    def update(self, task: Task) -> Task:
        row = self.session.get(models.TaskModel, task.id)
        if row is None:
            raise KeyError(task.id)
        row.display_order = task.display_order
        row.title = task.title
        row.summary = task.summary
        row.script_source = task.script_source
        row.user_intent = task.user_intent
        row.user_prompt = task.user_prompt
        row.ai_prompt = task.ai_prompt
        row.final_prompt = task.final_prompt
        row.prompt_source = task.prompt_source.value
        row.generation_params = task.generation_params
        row.planned_duration_seconds = task.planned_duration_seconds
        row.state = task.state.value
        row.progress = task.progress
        row.primary_result_id = task.primary_result_id
        row.revision = task.revision
        row.approved_prompt_source = (
            task.approved_prompt_source.value if task.approved_prompt_source else None
        )
        row.approved_prompt_hash = task.approved_prompt_hash
        row.approved_at = task.approved_at
        row.approved_revision_id = task.approved_revision_id
        row.user_view_mode = task.user_view_mode
        row.ai_view_mode = task.ai_view_mode
        row.updated_at = task.updated_at
        self.replace_bindings(task.id, task.asset_bindings)
        self.session.flush()
        return task

    def delete(self, task_id: str) -> None:
        self.session.execute(delete(models.TaskModel).where(models.TaskModel.id == task_id))
        self.session.flush()

    def count_by_project(self, project_id: str) -> int:
        value = self.session.scalar(
            select(func.count())
            .select_from(models.TaskModel)
            .where(models.TaskModel.project_id == project_id)
        )
        return int(value or 0)

    def next_display_order(self, project_id: str) -> int:
        value = self.session.scalar(
            select(func.max(models.TaskModel.display_order)).where(
                models.TaskModel.project_id == project_id
            )
        )
        return int(value or 0) + 1

    def replace_bindings(self, task_id: str, bindings: list[TaskAssetBinding]) -> None:
        self.session.execute(
            delete(models.TaskAssetBindingModel).where(
                models.TaskAssetBindingModel.task_id == task_id
            )
        )
        for binding in bindings:
            self.session.add(
                models.TaskAssetBindingModel(
                    task_id=task_id,
                    asset_id=binding.asset_id,
                    reference=binding.reference,
                    role=binding.role,
                    order_index=binding.order_index,
                )
            )
        self.session.flush()

    def reorder(self, project_id: str, task_ids: list[str]) -> None:
        for index, task_id in enumerate(task_ids, start=1):
            self.session.execute(
                update(models.TaskModel)
                .where(models.TaskModel.project_id == project_id, models.TaskModel.id == task_id)
                .values(display_order=-index)
            )
            self.session.execute(
                update(models.TaskPlacementModel)
                .where(models.TaskPlacementModel.task_id == task_id)
                .values(order_key=-index)
            )
        self.session.flush()
        for index, task_id in enumerate(task_ids, start=1):
            self.session.execute(
                update(models.TaskModel)
                .where(models.TaskModel.project_id == project_id, models.TaskModel.id == task_id)
                .values(display_order=index)
            )
            self.session.execute(
                update(models.TaskPlacementModel)
                .where(models.TaskPlacementModel.task_id == task_id)
                .values(order_key=index)
            )
        self.session.flush()
