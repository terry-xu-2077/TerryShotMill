from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

import folder_paths
import execution
from server import PromptServer
from .canvas_compiler import compile_canvas, prune_to_outputs


PREFIX = "/shotmill/v1"
PACKAGE_VERSION = "0.1.0"
ASSET_INDEX = Path(folder_paths.get_input_directory()) / "shotmill" / "assets.json"
RESULT_ROOT = Path(folder_paths.get_output_directory()) / "shotmill" / "results"
WORKFLOW_ROOT = Path(folder_paths.base_path) / "user" / "default" / "workflows"
JOB_INDEX = Path(folder_paths.get_output_directory()) / "shotmill" / "jobs.json"
NATIVE_SAVE_NODES = {
    "SaveImage",
    "SaveAnimatedWEBP",
    "SaveAnimatedPNG",
    "SaveVideo",
    "SaveWEBM",
    "SaveAudio",
    "SaveAudioMP3",
    "SaveAudioOpus",
    "SaveAudioAdvanced",
}
INPUT_LOADERS = {
    "LoadImage": ("IMAGE", "image"),
    "LoadVideo": ("VIDEO", "file"),
    "LoadAudio": ("AUDIO", "audio"),
    "PrimitiveString": ("STRING", "value"),
    "PrimitiveStringMultiline": ("TEXT", "value"),
}
BUS_PACK_TYPES = {"TerryXuWireBusPack", "TerryXuWirelessBusPack"}
BUS_UNPACK_TYPES = {"TerryXuWireBusUnpack", "TerryXuWirelessBusUnpack"}
BUS_TYPE = "TERRY_WIRE_BUS"
BRIDGE_IN_TYPES = {"ShotMillIOBridgeIn", "ShotMill.IOBridgeIn"}
BRIDGE_OUT_TYPES = {"ShotMillIOBridgeOut", "ShotMill.IOBridgeOut"}
LEGACY_BRIDGE_TYPES = {"ShotMillIOBridge", "ShotMill.IOBridge"}
LAST_WORKLOAD_KIND: str | None = None


def _safe_name(value: str, fallback: str) -> str:
    name = Path(value or fallback).name
    name = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]+", "_", name).strip(" .")
    return name or fallback


def _load_index(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_index(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _workflow_path(workflow_id: str) -> Path:
    root = WORKFLOW_ROOT.resolve()
    candidate = (root / workflow_id).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("workflowId must stay inside the Bridge workflow directory")
    if candidate.suffix.lower() != ".json" or not candidate.is_file():
        raise FileNotFoundError(workflow_id)
    return candidate


def _canvas_prompt(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return compile_canvas(raw)


def _load_prompt(workflow_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    path = _workflow_path(workflow_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("prompt"), dict):
        return raw["prompt"], raw
    if isinstance(raw, dict) and isinstance(raw.get("nodes"), list):
        return _canvas_prompt(raw), raw
    raise ValueError("workflow is neither a ComfyUI canvas workflow nor an API prompt")


def _replace_values(value: Any, payload: dict[str, Any]) -> Any:
    assets = payload.get("assetValues") if isinstance(payload.get("assetValues"), dict) else {}
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    final_prompt = str(payload.get("finalPrompt") or "")
    job_id = str(payload.get("jobId") or "")
    if isinstance(value, dict):
        return {key: _replace_values(item, payload) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_values(item, payload) for item in value]
    if not isinstance(value, str):
        return value
    if value == "{{final_prompt}}":
        return final_prompt
    if value == "{{job_id}}":
        return job_id
    if value == "{{seed}}":
        return payload.get("seed", 0)
    if value.startswith("{{asset:") and value.endswith("}}"):
        return assets.get(value[8:-2], value)
    if value.startswith("{{asset?:") and value.endswith("}}"):
        return assets.get(value[9:-2], value)
    if value.startswith("{{param:") and value.endswith("}}"):
        return params.get(value[8:-2], value)
    result = value.replace("{{final_prompt}}", final_prompt).replace("{{job_id}}", job_id)
    result = result.replace("{{seed}}", str(payload.get("seed", 0)))
    for key, item in assets.items():
        result = result.replace("{{asset:" + str(key) + "}}", str(item))
        result = result.replace("{{asset?:" + str(key) + "}}", str(item))
    for key, item in params.items():
        result = result.replace("{{param:" + str(key) + "}}", str(item))
    return result


def _bridge_kind(node: dict[str, Any] | None) -> str:
    if not isinstance(node, dict):
        return ""
    class_type = str(node.get("class_type") or node.get("type") or "")
    if class_type in BRIDGE_IN_TYPES:
        return "input"
    if class_type in BRIDGE_OUT_TYPES:
        return "output"
    if class_type in LEGACY_BRIDGE_TYPES:
        return "legacy"
    return ""


def _bridge_value_input(node: dict[str, Any]) -> Any:
    inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
    if "*" in inputs:
        return inputs["*"]
    return inputs.get("value")


def _bridge_input_values(node: dict[str, Any]) -> list[Any]:
    inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
    if "*" in inputs:
        return [
            value
            for name, value in inputs.items()
            if name == "*" or str(name).startswith("* ")
        ]
    if "value" in inputs:
        return [inputs["value"]]
    return []


def _rewrite_native_saves(prompt: dict[str, dict[str, Any]], job_id: str) -> None:
    safe_job = _safe_name(job_id, "job")
    bridge_outputs = {
        str(node_id)
        for node_id, node in prompt.items()
        if isinstance(node, dict)
        and _bridge_kind(node) in {"output", "legacy"}
        and isinstance(node.get("inputs"), dict)
        and isinstance(_bridge_value_input(node), list)
        and len(_bridge_value_input(node)) == 2
        and _loader_spec(prompt.get(str(_bridge_value_input(node)[0]))) is None
    }
    for node_id, node in prompt.items():
        if not isinstance(node, dict) or node.get("class_type") not in NATIVE_SAVE_NODES:
            continue
        inputs = node.setdefault("inputs", {})
        source = inputs.get("video") or inputs.get("images") or inputs.get("audio")
        if not isinstance(source, list) or len(source) != 2 or str(source[0]) not in bridge_outputs:
            continue
        original = str(inputs.get("filename_prefix") or f"output_{node_id}")
        stem = _safe_name(Path(original).name, f"output_{node_id}")
        inputs["filename_prefix"] = f"shotmill/results/{safe_job}/{stem}"


def _official_save_class(media_type: str) -> tuple[str, str] | None:
    normalized = _normalise_type(media_type)
    return {
        "IMAGE": ("SaveImage", "images"),
        "VIDEO": ("SaveVideo", "video"),
        "AUDIO": ("SaveAudio", "audio"),
    }.get(normalized)


def _rewrite_custom_saves(
    prompt: dict[str, dict[str, Any]], raw: dict[str, Any], job_id: str
) -> None:
    if not isinstance(raw, dict):
        return
    if isinstance(raw.get("prompt"), dict):
        nodes = [
            {"id": str(node_id), **node}
            for node_id, node in raw["prompt"].items()
            if isinstance(node, dict)
        ]
    else:
        nodes = raw.get("nodes", []) if isinstance(raw.get("nodes"), list) else []
    consumers = _all_consumers(raw, nodes)
    safe_job = _safe_name(job_id, "job")
    bridge_types = BRIDGE_IN_TYPES | BRIDGE_OUT_TYPES | LEGACY_BRIDGE_TYPES | BUS_PACK_TYPES | BUS_UNPACK_TYPES
    for node in nodes:
        if _bridge_kind(node) != "output":
            continue
        bridge_id = str(node.get("id"))
        for target_info in consumers.get((bridge_id, 0), []):
            target_id = str(target_info.get("targetNodeId") or "")
            target = prompt.get(target_id)
            if not isinstance(target, dict) or str(target.get("class_type") or "") in bridge_types:
                continue
            media_type = str(target_info.get("type") or "*")
            official = _official_save_class(media_type)
            if official is None:
                continue
            class_type, source_name = official
            old_inputs = target.get("inputs") if isinstance(target.get("inputs"), dict) else {}
            original = str(
                old_inputs.get("filename_prefix")
                or old_inputs.get("prefix")
                or old_inputs.get("filename")
                or f"output_{target_id}"
            )
            stem = _safe_name(Path(original).name, f"output_{target_id}")
            new_inputs: dict[str, Any] = {
                source_name: [bridge_id, 0],
                "filename_prefix": f"shotmill/results/{safe_job}/{stem}",
            }
            for key in ("format", "format.codec", "codec"):
                if key in old_inputs and not isinstance(old_inputs[key], list):
                    new_inputs[key] = old_inputs[key]
            target["class_type"] = class_type
            target["inputs"] = new_inputs


def _bind_input_markers(
    prompt: dict[str, dict[str, Any]], payload: dict[str, Any], raw: dict[str, Any] | None = None
) -> None:
    """Replace the file value of existing loader nodes behind Bridge In markers."""
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    asset_values = payload.get("assetValues") if isinstance(payload.get("assetValues"), dict) else {}
    markers: list[tuple[str, dict[str, Any], dict[str, Any], tuple[str, str], tuple[Any, ...], dict[str, Any]]] = []
    if isinstance(raw, dict):
        if isinstance(raw.get("prompt"), dict):
            raw_nodes = [
                {"id": str(node_id), **node}
                for node_id, node in raw["prompt"].items()
                if isinstance(node, dict)
            ]
        else:
            raw_nodes = raw.get("nodes", []) if isinstance(raw.get("nodes"), list) else []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict) or _bridge_kind(raw_node) not in {"input", "legacy"}:
                continue
            records = _bridge_source_records(raw, raw_nodes, raw_node)
            if not records:
                raise ValueError(f"Bridge In {raw_node.get('id')} must connect to a loader or bus input")
            for record in records:
                loader_id = str(record["loader"].get("id")) if record.get("loader") else ""
                loader = prompt.get(loader_id)
                if loader is None and loader_id:
                    original = record["loader"]
                    loader = {"class_type": original.get("class_type") or original.get("type"),
                              "inputs": dict(original.get("widgets_values_named") or {})}
                    prompt[loader_id] = loader
                spec = _loader_spec(loader)
                if not isinstance(loader, dict):
                    raise ValueError(f"Bridge In {raw_node.get('id')} has an invalid loader mapping")
                if spec is None:
                    spec = record.get("spec")
                    replacement = str(record.get("replacement") or "")
                    if not isinstance(spec, tuple) or not replacement:
                        raise ValueError(f"Bridge In {raw_node.get('id')} has an unsupported input type")
                    loader["class_type"] = replacement
                    loader["inputs"] = {}
                target = next(
                    (item for item in record.get("targets", []) if isinstance(item, dict)),
                    {},
                )
                order = (
                    (0, str(target.get("targetNodeId") or ""), int(target.get("targetSlot") or 0), str(target.get("name") or ""))
                    if target
                    else tuple(record.get("order", (9, 0)))
                )
                markers.append((str(raw_node.get("id")), prompt.get(str(raw_node.get("id")), {}), loader, spec, order, record))
    else:
        for node_id, node in prompt.items():
            if not isinstance(node, dict) or _bridge_kind(node) not in {"input", "legacy"}:
                continue
            values = _bridge_input_values(node)
            if not values:
                raise ValueError(f"Bridge In {node_id} must connect to a loader or bus input")
            for value in values:
                if not isinstance(value, list) or len(value) != 2:
                    raise ValueError(f"Bridge In {node_id} must connect to a loader or bus input")
                for loader, spec in _bridge_input_sources(prompt, value):
                    markers.append((str(node_id), node, loader, spec, (9, len(markers)), {}))
    markers.sort(key=lambda item: item[4])
    if not markers:
        return
    media_markers = [item for item in markers if item[3][0] not in {"STRING", "TEXT"}]
    slots = payload.get("inputSlots")
    if slots is None:
        slots = assets + [None] * (len(media_markers) - len(assets))
    if not isinstance(slots, list) or len(slots) != len(media_markers):
        raise ValueError(
            f"workflow declares {len(media_markers)} media inputs but job provides {len(assets)} assets"
        )
    media_index = 0
    assigned_records = []
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    for _, _marker, loader, loader_spec, _order, record in markers:
        expected_type, input_name = loader_spec
        targets = record.get("targets", [])
        loader_id = next((node_id for node_id, item in prompt.items() if item is loader), "")

        def connect_targets(connected: bool) -> None:
            for target in targets:
                receiver = prompt.get(str(target.get("targetNodeId")))
                if not receiver:
                    continue
                name = str(target.get("name") or "")
                inputs = receiver.setdefault("inputs", {})
                if connected:
                    inputs[name] = [loader_id, 0]
                else:
                    inputs.pop(name, None)
        if expected_type in {"STRING", "TEXT"}:
            targets = record.get("targets") if isinstance(record, dict) else []
            target_name = str(targets[0].get("name") or "") if targets and isinstance(targets[0], dict) else ""
            value = params.get(target_name) if target_name else None
            if value is None and target_name:
                value = params.get(target_name.replace(".", "_"))
            if value is None:
                value = payload.get("finalPrompt") or ""
            loader.setdefault("inputs", {})[input_name] = str(value)
            connect_targets(True)
            continue

        asset = slots[media_index]
        media_index += 1
        assigned_records.append((record, asset))
        if asset is None:
            connect_targets(False)
            continue
        if not isinstance(asset, dict):
            raise ValueError("invalid input slot asset")
        reference = str(asset.get("reference") or "")
        path = str(asset_values.get(reference) or "")
        if not path:
            raise ValueError(f"missing uploaded asset for Bridge media input {media_index}")
        media_type = str(asset.get("mediaType") or "image").lower()
        actual_type = {"image": "IMAGE", "video": "VIDEO", "audio": "AUDIO"}.get(
            media_type,
            media_type.upper(),
        )
        if expected_type != actual_type:
            raise ValueError(
                f"Bridge media input {media_index} uses {expected_type} loader but received {actual_type} asset"
            )
        loader.setdefault("inputs", {})[input_name] = path
        connect_targets(True)
    _adapt_h3_reference_labels(prompt, assigned_records)


def _adapt_h3_reference_labels(
    prompt: dict[str, dict[str, Any]], assigned_records: list[tuple[dict[str, Any], Any]]
) -> None:
    """H3 enumerates present references, not physical Autogrow socket suffixes."""
    import re

    by_node: dict[str, dict[str, dict[int, str]]] = {}
    pattern = re.compile(r"(?:^|\.)(ref_image|ref_video_audio|ref_video|ref_audio)_(\d+)$")
    for record, asset in assigned_records:
        for target in record.get("targets", []):
            node_id = str(target.get("targetNodeId"))
            if prompt.get(node_id, {}).get("class_type") != "MiniMaxH3ReferenceToVideo":
                continue
            match = pattern.search(str(target.get("name") or ""))
            if match:
                group = by_node.setdefault(node_id, {}).setdefault(match[1], {})
                if isinstance(asset, dict):
                    group[int(match[2])] = str(asset.get("reference") or "")

    for node_id, groups in by_node.items():
        mapping: dict[str, str] = {}
        counts = {"Picture": 0, "Video": 0, "Audio": 0}

        def label(reference: str, kind: str) -> None:
            counts[kind] += 1
            value = f"<{kind} {counts[kind]}>"
            if reference in mapping and mapping[reference] != value:
                raise ValueError("H3 reference is assigned to multiple input slots")
            mapping[reference] = value

        for _, reference in sorted(groups.get("ref_image", {}).items()):
            label(reference, "Picture")
        videos = groups.get("ref_video", {})
        soundtracks = groups.get("ref_video_audio", {})
        if set(soundtracks) - set(videos):
            raise ValueError("H3 video soundtrack requires the paired reference video")
        for index, reference in sorted(videos.items()):
            if index in soundtracks:
                label(soundtracks[index], "Audio")
            label(reference, "Video")
        for _, reference in sorted(groups.get("ref_audio", {}).items()):
            label(reference, "Audio")
        inputs = prompt[node_id].setdefault("inputs", {})
        text = inputs.get("prompt")
        if isinstance(text, list) and len(text) == 2:
            text = prompt.get(str(text[0]), {}).get("inputs", {}).get("value")
        if not isinstance(text, str):
            if any(old != new for old, new in mapping.items()):
                raise ValueError("H3 sparse references require a Bridge text input to remap prompt labels")
            continue
        missing = set(re.findall(r"<(?:Picture|Video|Audio)\s+\d+>", text)) - set(mapping)
        if missing:
            raise ValueError(f"H3 prompt references empty input slots: {', '.join(sorted(missing))}")
        # One substitution pass avoids collisions such as Picture 3 -> 2 -> 1.
        inputs["prompt"] = re.sub(r"<(?:Picture|Video|Audio)\s+\d+>", lambda match: mapping.get(match[0], match[0]), text)


def _bridge_markers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(raw.get("prompt"), dict):
        nodes = [
            {"id": str(node_id), **node}
            for node_id, node in raw["prompt"].items()
            if isinstance(node, dict)
        ]
        links: list[Any] = []
    else:
        nodes = raw.get("nodes", []) if isinstance(raw.get("nodes"), list) else []
        links = raw.get("links", []) if isinstance(raw.get("links"), list) else []
    return [
        {"node": node, "links": links, "nodes": nodes}
        for node in nodes
        if isinstance(node, dict)
        and bool(_bridge_kind(node))
    ]


def _normalise_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text or text in {"*", "ANY", "UNKNOWN"}:
        return "*"
    if "IMAGE" in text:
        return "IMAGE"
    if "VIDEO" in text:
        return "VIDEO"
    if "AUDIO" in text:
        return "AUDIO"
    return text


def _guess_type(input_name: str, node_type: str) -> str:
    text = f"{input_name} {node_type}".lower()
    if any(token in text for token in ("video", "movie", "frames")):
        return "VIDEO"
    if any(token in text for token in ("audio", "sound", "wave")):
        return "AUDIO"
    if any(token in text for token in ("image", "images", "frame", "picture")):
        return "IMAGE"
    if any(token in text for token in ("text", "prompt", "caption")):
        return "TEXT"
    if any(token in text for token in ("string", "str")):
        return "STRING"
    return "*"


def _loader_spec(node: dict[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(node, dict):
        return None
    spec = INPUT_LOADERS.get(str(node.get("class_type") or node.get("type") or ""))
    return spec


def _is_bus_pack(node: dict[str, Any] | None) -> bool:
    if not isinstance(node, dict):
        return False
    return str(node.get("class_type") or node.get("type") or "") in BUS_PACK_TYPES


def _bus_loader_sources(
    prompt: dict[str, dict[str, Any]],
    bus_node: dict[str, Any] | None,
    links: list[Any] | None = None,
) -> list[tuple[dict[str, Any], tuple[str, str]]]:
    if not _is_bus_pack(bus_node):
        return []
    inputs = bus_node.get("inputs") if isinstance(bus_node.get("inputs"), dict) else {}
    if isinstance(bus_node.get("inputs"), list):
        inputs = {}
        for index, item in enumerate(bus_node["inputs"]):
            if not isinstance(item, dict) or item.get("link") is None:
                continue
            link = _canvas_link({"links": links or []}, item["link"])
            if isinstance(link, (list, tuple)) and len(link) >= 3:
                inputs[str(item.get("name") or index)] = [link[1], link[2]]
            elif isinstance(link, dict):
                inputs[str(item.get("name") or index)] = [
                    link.get("origin_id", link.get("originId")),
                    link.get("origin_slot", link.get("originSlot", 0)),
                ]
    sources: list[tuple[dict[str, Any], tuple[str, str]]] = []
    for value in inputs.values():
        if not isinstance(value, list) or len(value) != 2:
            continue
        loader = prompt.get(str(value[0]))
        spec = _loader_spec(loader)
        if spec is not None and isinstance(loader, dict):
            sources.append((loader, spec))
    return sources


def _bridge_input_sources(
    prompt: dict[str, dict[str, Any]], value: list[Any]
) -> list[tuple[dict[str, Any], tuple[str, str]]]:
    source_node = prompt.get(str(value[0]))
    direct_spec = _loader_spec(source_node)
    if direct_spec is not None and isinstance(source_node, dict):
        return [(source_node, direct_spec)]
    return _bus_loader_sources(prompt, source_node)


def _canvas_link(raw: dict[str, Any], link_id: Any) -> Any:
    for link in raw.get("links", []) if isinstance(raw.get("links"), list) else []:
        if isinstance(link, (list, tuple)) and len(link) >= 6 and str(link[0]) == str(link_id):
            return link
        if isinstance(link, dict) and str(link.get("id")) == str(link_id):
            return link
    return None


def _all_consumers(raw: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[tuple[str, int], list[dict[str, Any]]]:
    consumers: dict[tuple[str, int], list[dict[str, Any]]] = {}
    by_id = {str(node.get("id")): node for node in nodes}

    def add(origin_id: Any, origin_slot: Any, target_id: Any, target_slot: Any, name: str, value_type: Any) -> None:
        target = by_id.get(str(target_id), {})
        target_type = _normalise_type(value_type)
        if target_type == "*":
            target_type = _guess_type(name, str(target.get("class_type") or target.get("type") or ""))
        consumers.setdefault((str(origin_id), int(origin_slot or 0)), []).append(
            {
                "targetNodeId": str(target_id),
                "targetSlot": int(target_slot or 0),
                "name": name,
                "type": target_type,
            }
        )

    if isinstance(raw.get("prompt"), dict):
        for node in nodes:
            inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
            for name, value in inputs.items():
                if isinstance(value, list) and len(value) == 2:
                    add(value[0], value[1], node.get("id"), 0, str(name), "*")
        return consumers

    for link in raw.get("links", []) if isinstance(raw.get("links"), list) else []:
        if isinstance(link, (list, tuple)) and len(link) >= 6:
            target = by_id.get(str(link[3]), {})
            specs = target.get("inputs") if isinstance(target.get("inputs"), list) else []
            target_spec = next(
                (item for item in specs if isinstance(item, dict) and int(item.get("slot_index", -1)) == int(link[4])),
                specs[int(link[4])] if 0 <= int(link[4]) < len(specs) else {},
            )
            add(link[1], link[2], link[3], link[4], str(target_spec.get("name") or f"input_{link[4]}"), link[5])
        elif isinstance(link, dict):
            origin_id = link.get("origin_id", link.get("originId"))
            target_id = link.get("target_id", link.get("targetId"))
            if origin_id is None or target_id is None:
                continue
            target_slot = link.get("target_slot", link.get("targetSlot", 0))
            target = by_id.get(str(target_id), {})
            specs = target.get("inputs") if isinstance(target.get("inputs"), list) else []
            target_spec = next(
                (item for item in specs if isinstance(item, dict) and int(item.get("slot_index", -1)) == int(target_slot or 0)),
                specs[int(target_slot or 0)] if 0 <= int(target_slot or 0) < len(specs) else {},
            )
            add(
                origin_id,
                link.get("origin_slot", link.get("originSlot", 0)),
                target_id,
                target_slot,
                str(target_spec.get("name") or f"input_{target_slot}"),
                link.get("type"),
            )
    return consumers


def _consumer_links(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[tuple[str, int], dict[str, Any]]]:
    if isinstance(raw.get("prompt"), dict):
        nodes = [
            {"id": str(node_id), **node}
            for node_id, node in raw["prompt"].items()
            if isinstance(node, dict)
        ]
        consumers: dict[tuple[str, int], dict[str, Any]] = {}
        for node in nodes:
            inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
            for name, value in inputs.items():
                if isinstance(value, list) and len(value) == 2:
                    consumers[(str(value[0]), int(value[1]))] = {
                        "name": str(name),
                        "type": _guess_type(str(name), str(node.get("class_type") or "")),
                        "nodeId": str(node["id"]),
                    }
        return nodes, consumers

    nodes = [node for node in raw.get("nodes", []) if isinstance(node, dict)] if isinstance(raw.get("nodes"), list) else []
    by_id = {str(node.get("id")): node for node in nodes}
    consumers: dict[tuple[str, int], dict[str, Any]] = {}
    for link in raw.get("links", []) if isinstance(raw.get("links"), list) else []:
        if isinstance(link, (list, tuple)) and len(link) >= 6:
            target = by_id.get(str(link[3]), {})
            target_inputs = target.get("inputs") if isinstance(target.get("inputs"), list) else []
            target_spec = next(
                (
                    item
                    for item in target_inputs
                    if isinstance(item, dict) and int(item.get("slot_index", -1)) == int(link[4])
                ),
                {},
            )
            name = str(target_spec.get("name") or f"input_{link[4]}")
            consumers[(str(link[1]), int(link[2]))] = {
                "originId": str(link[1]),
                "originSlot": int(link[2]),
                "targetId": str(link[3]),
                "targetSlot": int(link[4]),
                "type": _normalise_type(link[5]),
                "name": name,
            }
            declared = _normalise_type(target_spec.get("type"))
            if declared != "*":
                consumers[(str(link[1]), int(link[2]))]["type"] = declared
            if consumers[(str(link[1]), int(link[2]))]["type"] == "*":
                consumers[(str(link[1]), int(link[2]))]["type"] = _guess_type(
                    name, str(target.get("type") or "")
                )
        elif isinstance(link, dict):
            origin_id = link.get("origin_id", link.get("originId"))
            origin_slot = link.get("origin_slot", link.get("originSlot", 0))
            target_id = link.get("target_id", link.get("targetId"))
            target_slot = link.get("target_slot", link.get("targetSlot", 0))
            if origin_id is None or target_id is None:
                continue
            target = by_id.get(str(target_id), {})
            target_inputs = target.get("inputs") if isinstance(target.get("inputs"), list) else []
            target_spec = next(
                (
                    item
                    for item in target_inputs
                    if isinstance(item, dict) and int(item.get("slot_index", -1)) == int(target_slot or 0)
                ),
                {},
            )
            name = str(target_spec.get("name") or f"input_{target_slot}")
            key = (str(origin_id), int(origin_slot or 0))
            consumers[key] = {
                "originId": str(origin_id),
                "originSlot": int(origin_slot or 0),
                "targetId": str(target_id),
                "targetSlot": int(target_slot or 0),
                "name": name,
                "type": _normalise_type(link.get("type")),
            }
            declared = _normalise_type(target_spec.get("type"))
            if declared != "*":
                consumers[key]["type"] = declared
            if consumers[key]["type"] == "*":
                consumers[key]["type"] = _guess_type(name, str(target.get("type") or ""))
    return nodes, consumers


def _bridge_upstream_nodes(
    raw: dict[str, Any], nodes: list[dict[str, Any]], node: dict[str, Any]
) -> list[dict[str, Any] | None]:
    node_inputs = node.get("inputs") if isinstance(node.get("inputs"), (list, dict)) else []
    values: list[Any] = []
    if isinstance(node_inputs, dict):
        values = _bridge_input_values(node)
    else:
        for item in node_inputs:
            if isinstance(item, dict) and (
                item.get("name") == "value"
                or item.get("name") == "*"
                or str(item.get("name") or "").startswith("* ")
            ):
                values.append(item.get("link"))

    result: list[dict[str, Any] | None] = []
    for value in values:
        if isinstance(value, list) and len(value) == 2:
            upstream = value[0]
        else:
            upstream = value
        if upstream is None:
            result.append(None)
            continue
        if isinstance(raw.get("prompt"), dict):
            upstream_id = str(upstream)
        else:
            link = _canvas_link(raw, upstream)
            if isinstance(link, (list, tuple)) and len(link) >= 2:
                upstream_id = str(link[1])
            elif isinstance(link, dict):
                upstream_id = str(link.get("origin_id", link.get("originId")))
            else:
                upstream_id = ""
        result.append(next((item for item in nodes if str(item.get("id")) == upstream_id), None))
    return result


def _source_output_type(
    raw: dict[str, Any], source_id: Any, source_slot: Any, source_node: dict[str, Any] | None
) -> str:
    if not isinstance(raw.get("prompt"), dict):
        for link in raw.get("links", []) if isinstance(raw.get("links"), list) else []:
            if isinstance(link, (list, tuple)) and len(link) >= 6:
                if str(link[1]) == str(source_id) and int(link[2]) == int(source_slot or 0):
                    return _normalise_type(link[5])
            elif isinstance(link, dict):
                if str(link.get("origin_id", link.get("originId"))) == str(source_id) and int(link.get("origin_slot", link.get("originSlot", 0)) or 0) == int(source_slot or 0):
                    return _normalise_type(link.get("type"))
    return _guess_type("", str(source_node.get("class_type") or source_node.get("type") or "")) if source_node else "*"


def _bridge_upstream_refs(
    raw: dict[str, Any], nodes: list[dict[str, Any]], node: dict[str, Any]
) -> list[dict[str, Any]]:
    node_inputs = node.get("inputs") if isinstance(node.get("inputs"), (list, dict)) else []
    values: list[Any] = []
    if isinstance(node_inputs, dict):
        values = _bridge_input_values(node)
    else:
        for item in node_inputs:
            if isinstance(item, dict) and (
                item.get("name") == "value"
                or item.get("name") == "*"
                or str(item.get("name") or "").startswith("* ")
            ):
                values.append(item.get("link"))

    node_by_id = {str(item.get("id")): item for item in nodes if isinstance(item, dict)}
    refs: list[dict[str, Any]] = []
    for value in values:
        link_type = "*"
        if isinstance(value, list) and len(value) == 2:
            source_id, source_slot = value[0], value[1]
        else:
            link = _canvas_link(raw, value)
            if isinstance(link, (list, tuple)) and len(link) >= 6:
                source_id, source_slot, link_type = link[1], link[2], link[5]
            elif isinstance(link, dict):
                source_id = link.get("origin_id", link.get("originId"))
                source_slot = link.get("origin_slot", link.get("originSlot", 0))
                link_type = link.get("type")
            else:
                source_id, source_slot = None, 0
        source_node = node_by_id.get(str(source_id))
        refs.append({
            "node": source_node,
            "sourceId": str(source_id) if source_id is not None else "",
            "sourceSlot": int(source_slot or 0),
            "type": _normalise_type(link_type) if link_type != "*" else _source_output_type(raw, source_id, source_slot, source_node),
        })
    return refs


def _official_loader_spec(media_type: str) -> tuple[str, str, str] | None:
    normalized = _normalise_type(media_type)
    return {
        "IMAGE": ("IMAGE", "image", "LoadImage"),
        "VIDEO": ("VIDEO", "file", "LoadVideo"),
        "AUDIO": ("AUDIO", "audio", "LoadAudio"),
        "STRING": ("STRING", "value", "PrimitiveString"),
        "TEXT": ("TEXT", "value", "PrimitiveStringMultiline"),
    }.get(normalized)


def _bus_input_values(raw: dict[str, Any], bus_node: dict[str, Any]) -> list[Any]:
    inputs = bus_node.get("inputs")
    if isinstance(inputs, dict):
        return list(inputs.values())
    values: list[Any] = []
    for index, item in enumerate(inputs if isinstance(inputs, list) else []):
        if not isinstance(item, dict) or item.get("link") is None:
            continue
        link = _canvas_link(raw, item["link"])
        if isinstance(link, (list, tuple)) and len(link) >= 3:
            values.append([link[1], link[2]])
        elif isinstance(link, dict):
            values.append([
                link.get("origin_id", link.get("originId")),
                link.get("origin_slot", link.get("originSlot", 0)),
            ])
    return values


def _bus_lane_targets(
    raw: dict[str, Any],
    nodes: list[dict[str, Any]],
    bus_node: dict[str, Any],
    consumers: dict[tuple[str, int], list[dict[str, Any]]],
    lane_index: int,
) -> list[dict[str, Any]]:
    bus_id = str(bus_node.get("id"))
    lanes = bus_node.get("properties", {}).get("terry_wire_bus_lanes", [])
    lane = lanes[lane_index] if isinstance(lanes, list) and lane_index < len(lanes) else {}
    lane_id = str(lane.get("id") or "") if isinstance(lane, dict) else ""
    pack_channel = str(bus_node.get("properties", {}).get("terry_wireless_bus_channel") or "")
    targets: list[dict[str, Any]] = []
    for unpack in nodes:
        unpack_type = str(unpack.get("class_type") or unpack.get("type") or "")
        if unpack_type not in BUS_UNPACK_TYPES:
            continue
        bus_values = _bus_input_values(raw, unpack)
        connected_by_wire = bool(bus_values and isinstance(bus_values[0], list) and len(bus_values[0]) == 2 and str(bus_values[0][0]) == bus_id)
        unpack_channel = str(unpack.get("properties", {}).get("terry_wireless_bus_channel") or "")
        connected_by_channel = unpack_type == "TerryXuWirelessBusUnpack" and bool(pack_channel) and pack_channel == unpack_channel
        if not connected_by_wire and not connected_by_channel:
            continue
        output_index = -1
        outputs = unpack.get("outputs") if isinstance(unpack.get("outputs"), list) else []
        stored_ids = unpack.get("properties", {}).get("terry_wire_bus_lane_ids", [])
        for index, output in enumerate(outputs):
            output_lane = str(output.get("terry_lane_id") or "") if isinstance(output, dict) else ""
            if not output_lane and isinstance(stored_ids, list) and index < len(stored_ids):
                output_lane = str(stored_ids[index] or "")
            if not output_lane and index == lane_index:
                output_lane = lane_id
            if output_lane == lane_id or (not lane_id and index == lane_index):
                output_index = index
                break
        if output_index < 0:
            continue
        targets.extend(consumers.get((str(unpack.get("id")), output_index), []))
    return targets


def _final_targets(
    raw: dict[str, Any],
    nodes: list[dict[str, Any]],
    consumers: dict[tuple[str, int], list[dict[str, Any]]],
    source_id: str,
    source_slot: int,
) -> list[dict[str, Any]]:
    """Follow routing nodes, retaining lane identity and terminal input slots."""
    by_id = {str(node.get("id")): node for node in nodes}
    visited: set[tuple[str, int]] = set()
    terminals: dict[tuple[str, int], dict[str, Any]] = {}

    def follow_output(node_id: str, slot: int) -> None:
        key = (node_id, slot)
        if key in visited:
            return
        visited.add(key)
        for target in consumers.get(key, []):
            follow_target(target)

    def follow_target(target: dict[str, Any]) -> None:
        node_id = str(target["targetNodeId"])
        slot = int(target["targetSlot"])
        node = by_id.get(node_id, {})
        kind = str(node.get("class_type") or node.get("type") or "")
        if kind in BRIDGE_IN_TYPES | BRIDGE_OUT_TYPES | LEGACY_BRIDGE_TYPES | {"Reroute"}:
            follow_output(node_id, slot)
        elif kind in BUS_PACK_TYPES:
            key = (f"bus:{node_id}", slot)
            if key in visited:
                return
            visited.add(key)
            for terminal in _bus_lane_targets(raw, nodes, node, consumers, slot):
                follow_target(terminal)
        else:
            terminals[(node_id, slot)] = target

    follow_output(source_id, source_slot)
    return sorted(terminals.values(), key=lambda item: (
        str(item["targetNodeId"]), int(item["targetSlot"]), str(item["name"]),
    ))


def _bridge_source_records(
    raw: dict[str, Any], nodes: list[dict[str, Any]], bridge_node: dict[str, Any]
) -> list[dict[str, Any]]:
    consumers = _all_consumers(raw, nodes)
    node_by_id = {str(item.get("id")): item for item in nodes if isinstance(item, dict)}

    def visible_targets(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        hidden_types = BUS_PACK_TYPES | BUS_UNPACK_TYPES | BRIDGE_IN_TYPES | BRIDGE_OUT_TYPES | LEGACY_BRIDGE_TYPES
        for value in values:
            target = node_by_id.get(str(value.get("targetNodeId")))
            target_type = str(target.get("class_type") or target.get("type") or "") if target else ""
            if target_type in hidden_types:
                continue
            result.append(value)
        return result

    records: list[dict[str, Any]] = []
    bridge_id = str(bridge_node.get("id"))
    output_index = 0

    def bridge_output_targets(index: int) -> list[dict[str, Any]]:
        return _final_targets(raw, nodes, consumers, bridge_id, index)

    for input_index, ref in enumerate(_bridge_upstream_refs(raw, nodes, bridge_node)):
        upstream_node = ref.get("node")
        if upstream_node is None:
            output_index += 1
            continue
        if _is_bus_pack(upstream_node):
            for lane_index, value in enumerate(_bus_input_values(raw, upstream_node)):
                if not isinstance(value, list) or len(value) != 2:
                    continue
                loader = node_by_id.get(str(value[0]))
                spec = _loader_spec(loader)
                if not isinstance(loader, dict):
                    continue
                if spec is None:
                    inferred = _official_loader_spec(
                        _source_output_type(raw, value[0], value[1], loader)
                    )
                    if inferred is None:
                        continue
                    spec = inferred[:2]
                    replacement = inferred[2]
                else:
                    replacement = ""
                targets = bridge_output_targets(output_index)
                output_index += 1
                if not targets:
                    targets = _bus_lane_targets(raw, nodes, upstream_node, consumers, lane_index)
                if not targets:
                    targets = consumers.get((str(loader.get("id")), int(value[1] or 0)), [])
                records.append({
                    "loader": loader,
                    "spec": spec,
                    "replacement": replacement,
                    "targets": visible_targets(targets),
                    "order": (0, lane_index),
                })
            continue
        spec = _loader_spec(upstream_node)
        if spec is None:
            inferred = _official_loader_spec(str(ref.get("type") or "*"))
            if inferred is None:
                records.append({"loader": None, "spec": ("*", ""), "order": (9, input_index)})
                continue
            spec = inferred[:2]
            replacement = inferred[2]
        else:
            replacement = ""
        targets = bridge_output_targets(output_index)
        output_index += 1
        records.append({
            "loader": upstream_node,
            "spec": spec,
            "replacement": replacement,
            "targets": targets,
            "order": (1, input_index),
        })

    def sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
        targets = [item for item in record.get("targets", []) if isinstance(item, dict)]
        if targets:
            target = sorted(
                targets,
                key=lambda item: (
                    str(item.get("targetNodeId") or ""),
                    int(item.get("targetSlot") or 0),
                    str(item.get("name") or ""),
                ),
            )[0]
            return (0, str(target.get("targetNodeId") or ""), int(target.get("targetSlot") or 0), str(target.get("name") or ""))
        return tuple(record.get("order", (9, 0)))

    return sorted(records, key=sort_key)


def _bridge_ports(raw: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    nodes, consumers = _consumer_links(raw)
    inputs: list[dict[str, str]] = []
    outputs: list[dict[str, str]] = []
    used_names: set[str] = set()
    display_counts: dict[str, int] = {}
    input_index = 0
    output_index = 0
    for node in nodes:
        bridge_kind = _bridge_kind(node)
        if not bridge_kind:
            continue
        node_id = str(node.get("id"))
        downstream = consumers.get((node_id, 0))
        upstream_nodes = _bridge_upstream_nodes(raw, nodes, node)
        if bridge_kind == "input":
            for record in _bridge_source_records(raw, nodes, node):
                input_index += 1
                loader_type, loader_name = record["spec"]
                targets = [item for item in record.get("targets", []) if isinstance(item, dict)]
                target = targets[0] if targets else {}
                input_type = str(target.get("type") or loader_type)
                if input_type in {"", "*"}:
                    input_type = loader_type
                display_prefix = {
                    "IMAGE": "图片",
                    "VIDEO": "视频",
                    "AUDIO": "音频",
                    "STRING": "字符串",
                    "TEXT": "文本",
                }.get(input_type, "输入")
                display_counts[display_prefix] = display_counts.get(display_prefix, 0) + 1
                name = f"{display_prefix}{display_counts[display_prefix]}"
                target_port = str(target.get("name") or "")
                if name in used_names:
                    name = f"{name}_{input_index}"
                used_names.add(name)
                inputs.append({
                    "name": name,
                    "direction": "input",
                    "type": input_type,
                    "sourceNodeId": str(record["loader"].get("id")) if record.get("loader") else "",
                    "targetNodeId": str(target.get("targetNodeId") or ""),
                    "targetSlot": str(target.get("targetSlot", "")),
                    "targetPort": target_port,
                    "portName": target_port,
                })
            continue
        upstream_node = upstream_nodes[0] if upstream_nodes else None
        loader = _loader_spec(upstream_node)
        if loader is not None:
            input_index += 1
            input_type = loader[0]
            if input_type == "*" and downstream:
                input_type = downstream["type"]
            base_name = loader[1]
            name = base_name or f"input_{input_index}"
            if name in used_names:
                name = f"{name}_{input_index}"
            used_names.add(name)
            inputs.append({"name": name, "direction": "input", "type": input_type})
        elif upstream_node is not None:
            output_index += 1
            output_type = "*"
            if isinstance(raw.get("prompt"), dict):
                if downstream:
                    output_type = downstream["type"]
            else:
                refs = _bridge_upstream_refs(raw, nodes, node)
                if refs:
                    output_type = str(refs[0].get("type") or "*")
                if output_type == "*" and downstream:
                    output_type = downstream["type"]
            name = f"output_{output_index}"
            used_names.add(name)
            outputs.append({"name": name, "direction": "output", "type": output_type})
        else:
            input_index += 1
            input_type = downstream["type"] if downstream else "*"
            name = str(downstream.get("name") if downstream else f"input_{input_index}")
            if name in used_names:
                name = f"{name}_{input_index}"
            used_names.add(name)
            inputs.append({"name": name, "direction": "input", "type": input_type})
    return inputs, outputs


def _inspect(path: Path) -> dict[str, Any] | None:
    relative = path.relative_to(WORKFLOW_ROOT).as_posix()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    prompt = raw.get("prompt") if isinstance(raw, dict) else None
    fmt = "api" if isinstance(prompt, dict) else "canvas"
    markers = _bridge_markers(raw if isinstance(raw, dict) else {})
    inputs, outputs = _bridge_ports(raw if isinstance(raw, dict) else {})
    if not markers:
        return None
    return {
        "id": relative,
        "name": str((raw.get("extra") or {}).get("workflow_name") or path.stem)
        if isinstance(raw, dict)
        else path.stem,
        "fileName": path.name,
        "relativePath": relative,
        "format": fmt,
        "executable": True,
        "execution": "shotmill_bridge",
        "hasShotmillBridge": True,
        "inputs": inputs,
        "outputs": outputs,
        "warnings": [],
    }


async def _health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "version": PACKAGE_VERSION, "package": "ComfyUI-ShotMill"})


async def _workflows(_: web.Request) -> web.Response:
    WORKFLOW_ROOT.mkdir(parents=True, exist_ok=True)
    workflows = [
        item
        for path in sorted(WORKFLOW_ROOT.rglob("*.json"))
        if (item := _inspect(path)) is not None
    ]
    return web.json_response({"ok": True, "workflows": workflows})


async def _upload_asset(request: web.Request) -> web.Response:
    reader = await request.multipart()
    asset_id = ""
    role = ""
    filename = "asset.bin"
    content = b""
    async for field in reader:
        if field.name == "asset_id":
            asset_id = (await field.text()).strip()
        elif field.name == "role":
            role = (await field.text()).strip()
        elif field.name == "file" and field.filename:
            filename = _safe_name(field.filename, "asset.bin")
            content = await field.read()
    if not asset_id or not content:
        return web.json_response({"ok": False, "error": "asset_id and file are required"}, status=400)
    digest = hashlib.sha256(content).hexdigest()
    target_dir = Path(folder_paths.get_input_directory()) / "shotmill" / "assets" / _safe_name(asset_id, "asset")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(content)
    index = _load_index(ASSET_INDEX)
    items = index.setdefault("assets", {})
    item = {
        "assetId": asset_id,
        "role": role,
        "filename": filename,
        "relativePath": target.relative_to(Path(folder_paths.get_input_directory())).as_posix(),
        "sha256": digest,
        "size": len(content),
    }
    items[asset_id] = item
    _save_index(ASSET_INDEX, index)
    return web.json_response({"ok": True, "asset": item})


async def _assets(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "assets": list(_load_index(ASSET_INDEX).get("assets", {}).values())})


async def _prepare_runtime(request: web.Request) -> web.Response:
    global LAST_WORKLOAD_KIND
    payload = await request.json()
    kind = str(payload.get("kind") or "")
    previous = LAST_WORKLOAD_KIND
    released = bool(previous and previous != kind)
    if released:
        queue = PromptServer.instance.prompt_queue
        queue.set_flag("unload_models", True)
        queue.set_flag("free_memory", True)
    LAST_WORKLOAD_KIND = kind or previous
    return web.json_response({"ok": True, "released": released, "kind": LAST_WORKLOAD_KIND})


def _history_results(entry: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    outputs = entry.get("outputs") if isinstance(entry.get("outputs"), dict) else {}
    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        for output_type, items in node_output.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                result = dict(item)
                result["nodeId"] = str(node_id)
                result["nodeOutputType"] = output_type
                result["folder"] = str(result.get("type") or "output")
                result["relativePath"] = "/".join(
                    part.strip("/\\")
                    for part in (str(result.get("subfolder") or ""), str(result["filename"]))
                    if part
                )
                if result not in results:
                    results.append(result)
    return results


def _job_state(job_id: str) -> dict[str, Any]:
    index = _load_index(JOB_INDEX)
    item = index.get("jobs", {}).get(job_id) if isinstance(index.get("jobs"), dict) else None
    if not isinstance(item, dict):
        return {"ok": False, "jobId": job_id, "status": "not_found", "results": []}
    cached = item.get("terminalState")
    if isinstance(cached, dict) and cached.get("status") in {"completed", "failed"}:
        return cached
    prompt_id = str(item.get("promptId") or "")
    queue = PromptServer.instance.prompt_queue
    # Snapshot live work first; history then catches a completion between the reads.
    running, pending = queue.get_current_queue()
    history = queue.get_history(prompt_id=prompt_id)
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not isinstance(entry, dict):
        state = "not_found"
        if any(row[1] == prompt_id for row in running):
            state = "running"
        elif any(row[1] == prompt_id for row in pending):
            state = "queued"
        return {
            "ok": state != "not_found", "jobId": job_id, "promptId": prompt_id,
            "status": state, "results": [],
        }
    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    status_text = str(status.get("status_str") or "")
    if status_text in {"error", "failed"}:
        state = {
            "ok": False,
            "jobId": job_id,
            "promptId": prompt_id,
            "status": "failed",
            "error": status,
            "results": [],
        }
    else:
        state = {
            "ok": True,
            "jobId": job_id,
            "promptId": prompt_id,
            "status": "completed" if entry.get("outputs") is not None else "running",
            "results": _history_results(entry),
            "nodeOutputs": entry.get("outputs", {}),
        }
    if state["status"] in {"completed", "failed"}:
        item["terminalState"] = state
        _save_index(JOB_INDEX, index)
    return state


async def _create_job(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        job_id = _safe_name(str(payload.get("jobId") or ""), "job")
        workflow_id = str(payload.get("workflowId") or "").replace("\\", "/").strip("/")
        if isinstance(payload.get("prompt"), dict):
            prompt = payload["prompt"]
            raw = {"prompt": prompt}
        else:
            if not workflow_id:
                raise ValueError("workflowId or prompt is required")
            prompt, raw = _load_prompt(workflow_id)
            prompt = _replace_values(prompt, payload)
            _bind_input_markers(prompt, payload, raw)
            _rewrite_custom_saves(prompt, raw, job_id)
            _rewrite_native_saves(prompt, job_id)
        server = PromptServer.instance
        prompt_id = str(uuid.uuid4())
        server.node_replace_manager.apply_replacements(prompt)
        import nodes
        prompt = prune_to_outputs(prompt, {
            name for name, cls in nodes.NODE_CLASS_MAPPINGS.items() if getattr(cls, "OUTPUT_NODE", False)
        })
        valid = await execution.validate_prompt(prompt_id, prompt, None)
        if not valid[0]:
            return web.json_response(
                {"ok": False, "error": valid[1], "nodeErrors": valid[3]}, status=400
            )
        number = server.number
        server.number += 1
        extra_data = {
            "client_id": str(payload.get("clientId") or "shotmill"),
            "extra_pnginfo": {"workflow": raw},
            "create_time": int(time.time() * 1000),
        }
        server.prompt_queue.put(
            (number, prompt_id, prompt, extra_data, valid[2], {})
        )
        index = _load_index(JOB_INDEX)
        index.setdefault("jobs", {})[job_id] = {
            "jobId": job_id,
            "promptId": prompt_id,
            "workflowId": workflow_id,
            "createdAt": int(time.time()),
        }
        _save_index(JOB_INDEX, index)
        return web.json_response(
            {"ok": True, "jobId": job_id, "promptId": prompt_id, "status": "queued"}
        )
    except FileNotFoundError:
        return web.json_response({"ok": False, "error": "workflow_not_found"}, status=404)
    except (ValueError, json.JSONDecodeError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:  # pragma: no cover - ComfyUI runtime boundary
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def _job(request: web.Request) -> web.Response:
    state = _job_state(_safe_name(request.match_info["job_id"], "job"))
    return web.json_response(state, status=404 if state.get("status") == "not_found" else 200)


async def _result_metadata(request: web.Request) -> web.Response:
    return await _job(request)


async def _result_file(request: web.Request) -> web.StreamResponse:
    job_id = _safe_name(request.match_info["job_id"], "job")
    index = _load_index(JOB_INDEX)
    job = index.get("jobs", {}).get(job_id) if isinstance(index.get("jobs"), dict) else None
    if not isinstance(job, dict):
        raise web.HTTPNotFound()
    state = _job_state(job_id)
    try:
        result = state.get("results", [])[int(request.match_info["index"])]
    except (IndexError, ValueError, TypeError):
        raise web.HTTPNotFound()
    if not isinstance(result, dict):
        raise web.HTTPNotFound()
    root = Path(folder_paths.get_output_directory()).resolve()
    candidate = (root / str(result.get("subfolder") or "") / str(result.get("filename") or "")).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(candidate)


def register_routes() -> None:
    routes = PromptServer.instance.routes
    routes.get(f"{PREFIX}/health")(_health)
    routes.get(f"{PREFIX}/workflows")(_workflows)
    routes.post(f"{PREFIX}/assets")(_upload_asset)
    routes.get(f"{PREFIX}/assets")(_assets)
    routes.post(f"{PREFIX}/runtime/prepare")(_prepare_runtime)
    routes.post(f"{PREFIX}/jobs")(_create_job)
    routes.get(f"{PREFIX}/jobs/{{job_id}}")(_job)
    routes.get(f"{PREFIX}/results/{{job_id}}")(_result_metadata)
    routes.get(f"{PREFIX}/results/{{job_id}}/files/{{index}}")(_result_file)
