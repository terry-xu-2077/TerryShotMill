import math
from collections.abc import Sequence
from typing import Any

from shotmill.domain.application_settings import WorkflowNumericBinding
from shotmill.errors import ShotMillError


def port_key(port: dict[str, Any]) -> str:
    name = port.get("targetPort") or port.get("portName") or port.get("name", "")
    return f"{port.get('targetNodeId', '')}:{name}:{port.get('sourceNodeId', '')}"


def resolve_numeric_bindings(
    bindings: Sequence[WorkflowNumericBinding], ports: list[dict[str, Any]], duration: float,
) -> dict[str, float | int]:
    numeric_ports = {port_key(port): port for port in ports if port.get("type") in {"INT", "FLOAT"}}
    resolved: dict[str, float | int] = {}
    for binding in bindings:
        port = numeric_ports.get(binding.port_id)
        if port is None or binding.port_id in resolved:
            raise ShotMillError(
                "WORKFLOW_NUMERIC_BINDING_STALE", "档位中的数值输入已变化，请重新配置档位。", 422
            )
        value = binding.value
        if binding.source == "durationSeconds":
            value = duration
        elif binding.source == "frameCount":
            if (
                not math.isfinite(binding.fps) or binding.fps <= 0
                or binding.frame_multiple < 1
                or not 0 <= binding.frame_offset < binding.frame_multiple
            ):
                raise ShotMillError(
                    "WORKFLOW_FRAME_RULE_INVALID", "档位的帧率或帧数规则无效。", 422
                )
            value = (
                math.ceil((duration * binding.fps - binding.frame_offset) / binding.frame_multiple)
                * binding.frame_multiple + binding.frame_offset
            )
        elif binding.source != "constant":
            raise ShotMillError("WORKFLOW_NUMERIC_SOURCE_INVALID", "数值输入来源无效。", 422)
        if value is None or not math.isfinite(value):
            raise ShotMillError("WORKFLOW_NUMERIC_VALUE_INVALID", "数值输入必须是有限数字。", 422)
        if port["type"] == "INT":
            if value != int(value):
                raise ShotMillError(
                    "WORKFLOW_INTEGER_REQUIRED", "工作流要求整数，请检查档位数值。", 422
                )
            value = int(value)
        resolved[binding.port_id] = value
    return resolved
