from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from shotmill.domain.entities import Task, utcnow
from shotmill.domain.enums import PromptSource
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import NotFoundError, ShotMillError


@dataclass(frozen=True, slots=True)
class PromptReviewItem:
    task_id: str
    prompt_review_status: str
    approved_revision: int | None = None
    approved_at: datetime | None = None


def current_prompt_text(task: Task) -> str:
    return task.ai_prompt if task.prompt_source == PromptSource.AI else task.user_prompt


def prompt_hash(source: PromptSource, prompt: str) -> str:
    payload = f"{source.value}\0{prompt}".encode()
    return hashlib.sha256(payload).hexdigest()


def prompt_review_status(task: Task) -> str:
    prompt = current_prompt_text(task).strip()
    if not prompt:
        return "not_ready"
    if (
        task.approved_prompt_source == task.prompt_source
        and task.approved_prompt_hash == prompt_hash(task.prompt_source, prompt)
    ):
        return "approved"
    return "pending_review"


class PromptReviewService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self.uow_factory = uow_factory

    @staticmethod
    def item(task: Task) -> PromptReviewItem:
        return PromptReviewItem(
            task_id=task.id,
            prompt_review_status=prompt_review_status(task),
            approved_revision=task.revision if prompt_review_status(task) == "approved" else None,
            approved_at=task.approved_at,
        )

    def list_state(self, project_id: str) -> list[PromptReviewItem]:
        with self.uow_factory() as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError("PROJECT_NOT_FOUND", "Project not found")
            return [self.item(task) for task in uow.tasks.list_by_project(project_id)]

    def approve(self, project_id: str, task_id: str) -> PromptReviewItem:
        with self.uow_factory() as uow:
            task = uow.tasks.get(task_id)
            if task is None or task.project_id != project_id:
                raise NotFoundError("TASK_NOT_FOUND", "Task not found")
            prompt = current_prompt_text(task).strip()
            if not prompt:
                raise ShotMillError(
                    "PROMPT_NOT_READY",
                    "Current task has no prompt to approve",
                    422,
                )
            task.approved_prompt_source = task.prompt_source
            task.approved_prompt_hash = prompt_hash(task.prompt_source, prompt)
            task.approved_at = utcnow()
            task.approved_revision_id = None
            task.revision += 1
            task.updated_at = utcnow()
            uow.tasks.update(task)
            return self.item(task)
