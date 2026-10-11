"""Copy-on-write identity remapping. Media ownership must be rebound before saving."""

from copy import deepcopy
from dataclasses import dataclass

from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.application.project_transfer_validation import validate_project_transfer_graph
from shotmill.domain.entities import new_id


@dataclass
class RemappedProjectIdentity:
    source: ProjectTransferSource
    identities: dict[str, dict[str, str]]
    original_project_id: str


def remap_project_identity(source: ProjectTransferSource) -> RemappedProjectIdentity:
    """Remap a graph already validated by project import preflight."""
    result = deepcopy(source)
    mappings: dict[str, dict[str, str]] = {}

    def remap(kind: str, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        mapping = mappings.setdefault(kind, {})
        if value not in mapping:
            mapping[value] = new_id(kind)
        return mapping[value]

    original_project = source.project.id
    project_id = remap("project", original_project)
    result.project.id = project_id
    result.project.cover_asset_id = remap("asset", result.project.cover_asset_id)
    collections = (
        ("task", result.tasks), ("asset", result.assets), ("scene", result.scenes),
        ("job", result.jobs), ("result", result.results), ("promptrev", result.prompt_revisions),
        ("promptbatch", result.prompt_batches), ("promptjob", result.prompt_jobs),
        ("context", result.contexts),
    )
    for kind, items in collections:
        for item in items:
            item.id = remap(kind, item.id)
            item.project_id = project_id

    # Only schema-defined relationship keys are rewritten. Never replace text
    # occurrences in prompts/titles, filenames or cross-project provenance.
    keys = {
        "assetId": "asset", "sourceTaskId": "task", "sourceResultId": "result",
        "sourceJobId": "job",
    }

    def snapshot(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    value[key] = remap(keys[key], item)
                else:
                    snapshot(item)
        elif isinstance(value, list):
            for item in value:
                snapshot(item)

    for task in result.tasks:
        task.primary_result_id = remap("result", task.primary_result_id)
        task.approved_revision_id = remap("promptrev", task.approved_revision_id)
        for binding in task.asset_bindings:
            binding.asset_id = remap("asset", binding.asset_id)
        for revision in task.user_prompt_history:
            revision["id"] = remap("userprompt", revision["id"])
        snapshot(task.generation_params)
    for placement in result.placements:
        placement.task_id = remap("task", placement.task_id)
        placement.scene_id = remap("scene", placement.scene_id)
    for job in result.jobs:
        job.task_id = remap("task", job.task_id)
        snapshot(job.assets_snapshot)
        snapshot(job.params_snapshot)
        snapshot(job.context_snapshot)
        snapshot(job.execution_context)
        for link in job.context_snapshot.get("links", []):
            link["id"] = remap("context", link["id"])
    for item in result.results:
        item.task_id = remap("task", item.task_id)
        item.job_id = remap("job", item.job_id)
    for revision in result.prompt_revisions:
        revision.task_id = remap("task", revision.task_id)
        revision.asset_ids = [remap("asset", value) for value in revision.asset_ids]
    for job in result.prompt_jobs:
        job.task_id = remap("task", job.task_id)
        job.batch_id = remap("promptbatch", job.batch_id)
        job.revision_id = remap("promptrev", job.revision_id)
        snapshot(job.source_snapshot)
        snapshot(job.context_snapshot)
    for link in result.contexts:
        link.source_task_id = remap("task", link.source_task_id)
        link.target_task_id = remap("task", link.target_task_id)
        link.source_result_id = remap("result", link.source_result_id)
    validate_project_transfer_graph(result)
    return RemappedProjectIdentity(result, mappings, original_project)
