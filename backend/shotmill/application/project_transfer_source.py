"""Internal coherent source graph, NOT a portable/public serialization format.

Provider snapshots may contain machine configuration. The export serializer must
explicitly select portable fields and collect/pin files before releasing its UoW.
"""

from dataclasses import dataclass

from shotmill.domain.entities import (
    AiPromptRevision,
    Asset,
    ContextLink,
    Job,
    Project,
    PromptEnhancementBatch,
    PromptEnhancementJob,
    Result,
    Scene,
    Task,
    TaskPlacement,
)
from shotmill.domain.repositories import UnitOfWork
from shotmill.errors import ConflictError, NotFoundError


@dataclass
class ProjectTransferSource:
    project: Project
    assets: list[Asset]
    tasks: list[Task]
    scenes: list[Scene]
    placements: list[TaskPlacement]
    jobs: list[Job]
    results: list[Result]
    prompt_revisions: list[AiPromptRevision]
    prompt_batches: list[PromptEnhancementBatch]
    prompt_jobs: list[PromptEnhancementJob]
    contexts: list[ContextLink]


def read_project_transfer_source(uow: UnitOfWork, project_id: str) -> ProjectTransferSource:
    """Use a fresh UoW; caller retains transaction through portable staging.

The write reservation prevents submissions/deletions racing the active-job check.
Do not use UI lifecycle filters: archived and trashed tasks belong to the package.
Independent result archives deliberately do not belong to this graph.
"""
    uow.reserve_write()
    project = uow.projects.get(project_id)
    if project is None:
        raise NotFoundError("PROJECT_NOT_FOUND", "项目不存在。")
    if (uow.jobs.active_task_ids_by_project(project_id)
            or uow.prompt_jobs.active_task_ids_by_project(project_id)):
        raise ConflictError("PROJECT_TRANSFER_BUSY", "项目仍有活动任务，请结束后再导出。")
    tasks = uow.tasks.list_by_project(project_id)
    jobs, results, revisions, prompt_jobs, contexts = [], [], [], [], []
    for task in tasks:
        jobs.extend(uow.jobs.list_by_task(task.id))
        results.extend(uow.results.list_by_task(task.id))
        revisions.extend(uow.prompt_revisions.list_by_task(task.id))
        prompt_jobs.extend(uow.prompt_jobs.list_by_task(task.id))
        contexts.extend(uow.contexts.list_by_target(task.id))
    return ProjectTransferSource(
        project=project,
        assets=uow.assets.list_by_project(project_id), tasks=tasks,
        scenes=uow.story_structure.list_scenes(project_id),
        placements=uow.story_structure.list_placements(project_id),
        jobs=jobs, results=results, prompt_revisions=revisions,
        prompt_batches=uow.prompt_batches.list_by_project(project_id),
        prompt_jobs=prompt_jobs, contexts=contexts,
    )
