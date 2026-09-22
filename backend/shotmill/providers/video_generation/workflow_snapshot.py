"""Integrity checks for Bridge-owned, serializable workflow execution snapshots."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from shotmill.errors import ShotMillError


def checked_workflow_snapshot(value: Any, workflow_id: str) -> dict[str, Any]:
    try:
        if (
            not isinstance(value, dict)
            or value.get("version") != 1
            or value.get("workflowId") != workflow_id
            or not isinstance(value.get("raw"), dict)
            or not isinstance(value.get("prompt"), dict)
            or not value["prompt"]
            or not isinstance(value.get("inputs"), list)
        ):
            raise ValueError("invalid snapshot structure")
        content = {key: item for key, item in value.items() if key != "sha256"}
        encoded = json.dumps(
            content, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != value.get("sha256"):
            raise ValueError("snapshot digest mismatch")
    except (ValueError, TypeError) as exc:
        raise ShotMillError(
            "WORKFLOW_SNAPSHOT_INVALID", "工作流快照无效或已损坏，请重新提交生成。", 422,
        ) from exc
    return deepcopy(value)
