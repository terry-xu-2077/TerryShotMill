"""Preserve hidden Scene/Placement structure without exposing ORM to migration services."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from shotmill.domain.entities import Scene, TaskPlacement
from shotmill.persistence.models import SceneModel, TaskModel, TaskPlacementModel


class SqlAlchemyStoryStructureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_scenes(self, project_id: str) -> list[Scene]:
        rows = self.session.scalars(
            select(SceneModel).where(SceneModel.project_id == project_id)
            .order_by(SceneModel.order_key, SceneModel.id)
        )
        return [Scene(
            id=row.id, project_id=row.project_id, number=row.number,
            title=row.title, summary=row.summary, order_key=row.order_key,
        ) for row in rows]

    def list_placements(self, project_id: str) -> list[TaskPlacement]:
        # Filter through the task owner; a corrupt cross-project scene must remain
        # visible to the transfer validator, rather than silently disappearing.
        rows = self.session.scalars(
            select(TaskPlacementModel)
            .join(TaskModel, TaskModel.id == TaskPlacementModel.task_id)
            .where(TaskModel.project_id == project_id)
            .order_by(TaskPlacementModel.scene_id, TaskPlacementModel.order_key,
                      TaskPlacementModel.task_id)
        )
        return [TaskPlacement(row.task_id, row.scene_id, row.order_key) for row in rows]

    def add_scene(self, scene: Scene) -> Scene:
        self.session.add(SceneModel(
            id=scene.id, project_id=scene.project_id, number=scene.number,
            title=scene.title, summary=scene.summary, order_key=scene.order_key,
        ))
        self.session.flush()
        return scene

    def place_task(self, project_id: str, placement: TaskPlacement) -> None:
        task = self.session.get(TaskModel, placement.task_id)
        scene = self.session.get(SceneModel, placement.scene_id)
        if (task is None or scene is None or task.project_id != project_id
                or scene.project_id != project_id):
            raise ValueError("Task and scene must belong to the same project")
        row = self.session.get(TaskPlacementModel, placement.task_id)
        if row is None:
            self.session.add(TaskPlacementModel(
                task_id=placement.task_id, scene_id=placement.scene_id,
                order_key=placement.order_key,
            ))
        else:
            row.scene_id = placement.scene_id
            row.order_key = placement.order_key
        self.session.flush()
