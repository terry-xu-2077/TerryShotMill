"""Relationship preflight for a typed project transfer graph, before any writes.

JSON decoding/type validation and file verification are separate required gates.
"""

import re

from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.domain.enums import JobStatus
from shotmill.errors import ConflictError


def validate_project_transfer_graph(source: ProjectTransferSource) -> None:
    def require(condition: bool) -> None:
        if not condition:
            raise ConflictError("PROJECT_TRANSFER_GRAPH_INVALID", "项目包内部关联不完整或不合法。")

    project_id = source.project.id
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]{1,200}", project_id)))

    def index(items):
        result = {}
        for item in items:
            require(bool(re.fullmatch(r"[A-Za-z0-9_-]{1,200}", item.id)))
            require(item.id not in result and item.project_id == project_id)
            result[item.id] = item
        return result

    tasks, assets, scenes = index(source.tasks), index(source.assets), index(source.scenes)
    jobs, results = index(source.jobs), index(source.results)
    revisions = index(source.prompt_revisions)
    batches, prompt_jobs = index(source.prompt_batches), index(source.prompt_jobs)
    index(source.contexts)
    require(source.project.cover_asset_id is None or source.project.cover_asset_id in assets)
    for task in tasks.values():
        require(all(binding.asset_id in assets for binding in task.asset_bindings))
        if task.primary_result_id is not None:
            result = results.get(task.primary_result_id)
            require(result is not None and result.task_id == task.id)
        if task.approved_revision_id is not None:
            revision = revisions.get(task.approved_revision_id)
            require(revision is not None and revision.task_id == task.id)
    placements = set()
    for placement in source.placements:
        require(placement.task_id in tasks and placement.scene_id in scenes)
        require(placement.task_id not in placements)
        placements.add(placement.task_id)
    require(placements == set(tasks))
    for job in (*jobs.values(), *prompt_jobs.values()):
        require(job.task_id in tasks)
        require(job.status not in {JobStatus.QUEUED, JobStatus.RUNNING})
    for result in results.values():
        job = jobs.get(result.job_id)
        require(job is not None and job.task_id == result.task_id)
    for revision in revisions.values():
        require(revision.task_id in tasks)
    for job in prompt_jobs.values():
        require(job.batch_id in batches)
        if job.revision_id is not None:
            revision = revisions.get(job.revision_id)
            require(revision is not None and revision.task_id == job.task_id)
    for link in source.contexts:
        require(link.target_task_id in tasks)
        require(link.source_task_id != link.target_task_id)
        if link.source_deleted_at is not None:
            # Tombstones remain missing after import, never rebound to a live task.
            require(link.source_task_id not in tasks)
            continue
        require(link.source_task_id in tasks)
        if link.source_result_id is not None:
            result = results.get(link.source_result_id)
            require(result is not None and result.task_id == link.source_task_id)
