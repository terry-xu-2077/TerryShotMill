"""Portable records v1: explicit treatment of every open-ended dictionary.

Unknown creative parameters fail closed instead of silently losing settings.
Provider connection/runtime configuration is intentionally not portable.
"""

from dataclasses import asdict
from datetime import datetime
from enum import Enum
from math import isfinite

from shotmill.application.project_transfer_requirements import portable_provider_requirements
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.errors import ConflictError

PARAMETERS = frozenset("""
resolution quality mode contextMode contextStartSeconds contextEndSeconds contextDurationSeconds
durationSeconds seed seedMode profileId target workflowProfileId width height fps steps cfg
""".split())
MEDIA = frozenset("""
assetId reference role mediaType projectRelativePath originalFilename sourceTaskId sourceResultId
sourceSha256 sourceDurationSeconds startSeconds endSeconds audioIncluded sha256
""".split())


def _scalars(value: dict, allowed: frozenset[str]) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ConflictError("PROJECT_TRANSFER_SCHEMA_UNSUPPORTED", "项目含未支持的迁移字段。")
    result = {}
    for key, item in value.items():
        if item is not None and type(item) not in (str, int, float, bool):
            raise ConflictError("PROJECT_TRANSFER_SCHEMA_UNSUPPORTED", "迁移字段格式不受支持。")
        if isinstance(item, float) and not isfinite(item):
            raise ConflictError("PROJECT_TRANSFER_SCHEMA_UNSUPPORTED", "迁移字段含非法数值。")
        result[key] = item
    return result


def _parameters(value: dict) -> dict:
    plain = {key: item for key, item in value.items() if key != "workflowInputs"}
    result = _scalars(plain, PARAMETERS)
    if "workflowInputs" in value:
        selection = value["workflowInputs"]
        if selection is None:
            result["workflowInputs"] = None
        else:
            result["workflowInputs"] = {
                **_scalars({key: item for key, item in selection.items() if key != "slots"},
                           frozenset({"workflowId"})),
                "slots": [_scalars(item, frozenset({"portId", "assetId", "reference"}))
                          for item in selection.get("slots", [])],
            }
    return result


def _context(value: dict) -> dict:
    result = _scalars(
        {key: item for key, item in value.items()
         if key not in {"links", "media", "dependency", "warnings"}},
        frozenset({"mode", "requestedMode", "sourceJobId"}),
    )
    if "links" in value:
        result["links"] = [_scalars(item, frozenset({
            "id", "sourceTaskId", "kind", "sourceResultId", "stale",
        })) for item in value["links"]]
    if "media" in value:
        result["media"] = [_scalars(item, MEDIA) for item in value["media"]]
    if "dependency" in value:
        result["dependency"] = _scalars(value["dependency"], frozenset({
            "sourceJobId", "sourceTaskId", "mode",
        }))
    # Runtime warning prose may embed absolute paths or endpoint responses.
    return result


def _provenance(value: dict, depth: int = 0) -> dict:
    if depth > 32:
        raise ConflictError("PROJECT_TRANSFER_SCHEMA_UNSUPPORTED", "素材来源链过长。")
    result = _scalars(
        {key: item for key, item in value.items() if key not in {"params", "originalSource"}},
        frozenset({"sourceType", "sourceId", "projectId", "projectTitle", "assetName",
                   "taskId", "taskTitle", "resultId", "jobId", "generatedAt", "prompt",
                   "importedAt"}),
    )
    if "params" in value:
        result["params"] = _parameters(value["params"])
    if "originalSource" in value:
        result["originalSource"] = _provenance(value["originalSource"], depth + 1)
    return result


def _json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def serialize_project_transfer_records(source: ProjectTransferSource) -> dict:
    records = asdict(source)
    for task in records["tasks"]:
        task["generation_params"] = _parameters(task["generation_params"])
        task["user_prompt_history"] = [_scalars(item, frozenset({"id", "prompt", "createdAt"}))
                                       for item in task["user_prompt_history"]]
    for asset in records["assets"]:
        # Cross-project provenance is descriptive, never an executable dependency.
        asset["provenance"] = _provenance(asset["provenance"])
    for result in records["results"]:
        result["metadata"] = _scalars({
            key: item for key, item in result["metadata"].items() if key in {
                "contentType", "originalFilename", "durationSeconds", "width", "height",
                "fps", "sha256", "transferVerified",
            }
        }, frozenset({"contentType", "originalFilename", "durationSeconds", "width", "height",
                      "fps", "sha256", "transferVerified"}))
    for job in records["jobs"]:
        job["provider_profile_snapshot"] = {}
        job["provider_job_id"] = None
        job["runtime_progress"] = None
        job["error_message"] = None
        job["params_snapshot"] = _parameters(job["params_snapshot"])
        job["task_content_snapshot"] = _scalars(job["task_content_snapshot"], frozenset({
            "title", "summary", "userIntent", "plannedDurationSeconds", "promptSource",
            "taskRevision",
        }))
        job["generation_profile_snapshot"] = _scalars(
            job["generation_profile_snapshot"], frozenset({"profileId", "target"}),
        )
        job["assets_snapshot"] = [_scalars(item, MEDIA) for item in job["assets_snapshot"]]
        job["context_snapshot"] = _context(job["context_snapshot"])
        if job["execution_context"] is not None:
            job["execution_context"] = _context(job["execution_context"])
    for job in records["prompt_jobs"]:
        job["provider_profile_snapshot"] = {}
        job["error"] = None
        snapshot = job["source_snapshot"]
        job["source_snapshot"] = _scalars(
            {key: item for key, item in snapshot.items() if key != "media"},
            frozenset({"userPrompt", "durationSeconds", "taskRevision", "mode", "contextMode",
                       "forceAiSource"}),
        )
        job["source_snapshot"]["media"] = [_scalars(item, MEDIA)
                                            for item in snapshot.get("media", [])]
        context = job["context_snapshot"]
        job["context_snapshot"] = _scalars(
            {key: item for key, item in context.items() if key != "media"}, frozenset({
            "includeProjectBackground", "includePreviousTaskSummary", "projectBackground",
            "previousTaskSummary",
            }))
        if "media" in context:
            job["context_snapshot"]["media"] = [_scalars(item, MEDIA) for item in context["media"]]
    return {"schemaVersion": 1, **_json(records),
            "providerRequirements": portable_provider_requirements(source)}
