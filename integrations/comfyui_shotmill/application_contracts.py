from __future__ import annotations

import math
from typing import Any


def _adapt_h3_reference_labels(
    prompt: dict[str, dict[str, Any]], assigned_records: list[tuple[dict[str, Any], Any]]
) -> None:
    """H3 enumerates present references, not physical Autogrow socket suffixes."""
    import re

    by_node: dict[str, dict[str, dict[int, str]]] = {}
    pattern = re.compile(r"(?:^|\.)(ref_image|ref_video_audio|ref_video|ref_audio)_(\d+)$")
    for record, asset in assigned_records:
        targets = list(record.get("targets", []))
        for target in list(targets):
            decoder_id = str(target.get("targetNodeId"))
            if prompt.get(decoder_id, {}).get("class_type") == "GetVideoComponents":
                for consumer_id, consumer in prompt.items():
                    for name, value in consumer.get("inputs", {}).items():
                        if value == [decoder_id, 0]:
                            targets.append({"targetNodeId": consumer_id, "name": name})
        for target in targets:
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


def _bind_parameter_selectors(prompt: dict, params: Any) -> None:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    for node in prompt.values():
        kind = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if kind == "ShotMillResolutionSelector" and "resolution" in params:
            value = params["resolution"]
            if value not in {"480p", "720p", "1080p"}:
                raise ValueError("Unsupported resolution")
            inputs["resolution"] = value
        elif kind == "ShotMillDurationSelector" and "durationSeconds" in params:
            value = params["durationSeconds"]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 < value <= 60:
                raise ValueError("Invalid durationSeconds")
            inputs["seconds"] = value


def _disconnect_h3_optional(prompt: dict, receiver: dict, name: str, decoder_id: str) -> None:
    if receiver.get("class_type") != "GetVideoComponents" or name != "video":
        return
    for consumer in prompt.values():
        if consumer.get("class_type") != "MiniMaxH3ReferenceToVideo":
            continue
        inputs = consumer.get("inputs", {})
        for port, value in list(inputs.items()):
            if (port.startswith(("ref_videos.", "ref_video_audios."))
                and isinstance(value, list) and len(value) == 2 and str(value[0]) == decoder_id):
                inputs.pop(port)


class GenericContract:
    name = "generic"
    version = 1

    def bind_parameters(self, prompt: dict, params: Any) -> None:
        pass

    def adapt_references(self, prompt: dict, assignments: list) -> None:
        pass

    def disconnect_optional(self, prompt: dict, receiver: dict, name: str, node_id: str) -> None:
        pass


class ShotMillVideoContract(GenericContract):
    name = "shotmill.video"
    bind_parameters = staticmethod(_bind_parameter_selectors)
    adapt_references = staticmethod(_adapt_h3_reference_labels)
    disconnect_optional = staticmethod(_disconnect_h3_optional)


CONTRACTS = {(contract.name, contract.version): contract for contract in (
    GenericContract(), ShotMillVideoContract(),
)}


def resolve_application_contract(payload: dict, *, legacy: bool = True) -> GenericContract:
    declaration = payload.get("applicationContract")
    if declaration is None and legacy:
        declaration = {"name": "shotmill.video", "version": 1}
    if not isinstance(declaration, dict):
        raise ValueError("applicationContract with name and version is required")
    name, version = declaration.get("name"), declaration.get("version")
    if not isinstance(name, str) or type(version) is not int:
        raise ValueError("applicationContract name must be text and version an integer")
    contract = CONTRACTS.get((name, version))
    if contract is None:
        raise ValueError(f"Unsupported application contract: {name}@{version}")
    return contract


def contract_catalogue() -> list[dict]:
    return [{"name": name, "version": version} for name, version in CONTRACTS]

