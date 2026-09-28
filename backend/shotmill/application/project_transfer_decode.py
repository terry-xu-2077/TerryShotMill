"""Strict records-v1 decoding; never interpret package data as runtime configuration."""

import json
import re
from dataclasses import dataclass, fields

from pydantic import TypeAdapter, ValidationError

from shotmill.application.project_transfer_files import project_transfer_media_paths
from shotmill.application.project_transfer_records import serialize_project_transfer_records
from shotmill.application.project_transfer_source import ProjectTransferSource
from shotmill.application.project_transfer_validation import validate_project_transfer_graph
from shotmill.errors import ConflictError
from shotmill.media.project_package import _portable_path

_SOURCE = TypeAdapter(ProjectTransferSource)
_FIELDS = {item.name for item in fields(ProjectTransferSource)}


@dataclass(frozen=True)
class DecodedProjectTransfer:
    source: ProjectTransferSource
    provider_requirements: list[dict]


def decode_project_transfer_records(records: dict) -> DecodedProjectTransfer:
    def invalid():
        return ConflictError(
            "PROJECT_TRANSFER_RECORDS_INVALID", "项目包记录格式无效或版本不受支持。",
        )

    if (not isinstance(records, dict)
            or set(records) != _FIELDS | {"schemaVersion", "providerRequirements"}
            or type(records["schemaVersion"]) is not int or records["schemaVersion"] != 1):
        raise invalid()
    requirements = records["providerRequirements"]
    if not isinstance(requirements, list):
        raise invalid()
    for item in requirements:
        if (not isinstance(item, dict) or set(item) - {
            "kind", "requiresConfiguration", "providerId", "workflowId", "modelId",
            "workflowProfileId",
        } or not isinstance(item.get("kind"), str) or item.get("kind") not in {"video", "prompt"}
                or item.get("requiresConfiguration") is not True):
            raise invalid()
        provider = item.get("providerId")
        if "providerId" in item and (
            not isinstance(provider, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", provider)
        ):
            raise invalid()
        for key in ("workflowId", "modelId", "workflowProfileId"):
            if key in item:
                try:
                    _portable_path(item[key])
                except ValueError as exc:
                    raise invalid() from exc
    payload = {key: records[key] for key in _FIELDS}
    try:
        # Strict JSON validation accepts ISO dates/enums, but not stringified
        # numbers, booleans as integers, or arbitrary Python objects.
        source = _SOURCE.validate_json(json.dumps(payload, allow_nan=False), strict=True)
        canonical = serialize_project_transfer_records(source)
        canonical_payload = {key: canonical[key] for key in _FIELDS}
        # Also rejects unknown nested dataclass fields and omitted default fields;
        # Pydantic alone may otherwise silently ignore/fill those values.
        if json.dumps(payload, sort_keys=True) != json.dumps(canonical_payload, sort_keys=True):
            raise invalid()
        validate_project_transfer_graph(source)
        # Validate required media fields while malformed records are still
        # normalized to an import error, before manifest matching or any writes.
        project_transfer_media_paths(source)
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise invalid() from exc
    return DecodedProjectTransfer(source, json.loads(json.dumps(requirements)))
