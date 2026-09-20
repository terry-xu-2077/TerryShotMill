"""Compile saved canvas routing into an execution copy; never edit the saved graph."""

from __future__ import annotations

from typing import Any

PACK_TYPES = {"TerryXuWireBusPack", "TerryXuWirelessBusPack"}
UNPACK_TYPES = {"TerryXuWireBusUnpack", "TerryXuWirelessBusUnpack"}
VIRTUAL_TYPES = (
    PACK_TYPES
    | UNPACK_TYPES
    | {
        "SetNode",
        "GetNode",
        "Reroute",
        "Note",
        "MarkdownNote",
        "TerryXuGroupManager",
    }
)
MISSING = object()


def _links(graph: dict) -> dict[str, tuple[str, int, str, int]]:
    result = {}
    for link in graph.get("links", []):
        if isinstance(link, (list, tuple)):
            result[str(link[0])] = (str(link[1]), int(link[2]), str(link[3]), int(link[4]))
        elif isinstance(link, dict):
            result[str(link["id"])] = (
                str(link.get("origin_id", link.get("originId"))),
                int(link.get("origin_slot", link.get("originSlot", 0))),
                str(link.get("target_id", link.get("targetId"))),
                int(link.get("target_slot", link.get("targetSlot", 0))),
            )
    return result


def _widget_values(node: dict) -> dict:
    named = dict(node.get("widgets_values_named") or {})
    values = node.get("widgets_values", [])
    if not isinstance(values, list):
        return named
    index = 0
    for spec in node.get("inputs", []):
        widget = spec.get("widget")
        if widget is None:
            continue
        name = widget.get("name", spec.get("name"))
        if index < len(values):
            named.setdefault(name, values[index])
        index += 1
        # Comfy's seed controls serialize an extra frontend-only widget.
        if (
            name in {"seed", "noise_seed"}
            and index < len(values)
            and values[index]
            in (
                "fixed",
                "increment",
                "decrement",
                "randomize",
            )
        ):
            index += 1
    return named


def compile_canvas(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = {
        str(item["id"]): item for item in raw.get("definitions", {}).get("subgraphs", [])
    }
    prompt: dict[str, dict[str, Any]] = {}

    def scope(graph: dict, prefix: str, external: list, ancestry: tuple) -> dict[int, Any]:
        nodes = {str(item["id"]): item for item in graph.get("nodes", [])}
        links = _links(graph)
        widgets = {key: _widget_values(node) for key, node in nodes.items()}
        input_id = str(graph.get("inputNode", {}).get("id", -10))
        output_id = str(graph.get("outputNode", {}).get("id", -20))
        groups: dict[str, dict[int, Any]] = {}
        visiting: set[tuple[str, int]] = set()

        def input_value(node: dict, slot: int) -> Any:
            specs = node.get("inputs", [])
            if slot >= len(specs):
                return MISSING
            spec = specs[slot]
            link = links.get(str(spec.get("link")))
            if link:
                return resolve(link[0], link[1])
            return widgets[str(node["id"])].get(spec.get("name"), MISSING)

        def constant(node: dict) -> Any:
            values = node.get("widgets_values", [])
            return values[0] if isinstance(values, list) and values else None

        def resolve(node_id: str, slot: int) -> Any:
            if node_id == input_id:
                return external[slot] if slot < len(external) else MISSING
            node = nodes.get(node_id)
            if node is None or node.get("mode") == 2:
                return MISSING
            key = (node_id, slot)
            if key in visiting:
                raise ValueError(f"Routing cycle at {prefix}{node_id}:{slot}")
            visiting.add(key)
            try:
                kind = node.get("type")
                if node.get("mode") == 4:
                    outputs = node.get("outputs", [])
                    output_type = outputs[slot].get("type") if slot < len(outputs) else None
                    specs = node.get("inputs", [])
                    candidates = [
                        i
                        for i, spec in enumerate(specs)
                        if spec.get("link") is not None
                        and (output_type in (None, "*") or spec.get("type") in (output_type, "*"))
                    ]
                    index = slot if slot in candidates else next(iter(candidates), None)
                    return input_value(node, index) if index is not None else MISSING
                if kind in definitions:
                    if kind in ancestry:
                        raise ValueError(f"Recursive subgraph: {kind}")
                    if node_id not in groups:
                        groups[node_id] = scope(
                            definitions[kind],
                            f"{prefix}{node_id}:",
                            [input_value(node, i) for i in range(len(node.get("inputs", [])))],
                            (*ancestry, kind),
                        )
                    return groups[node_id].get(slot, MISSING)
                if kind in {"Reroute", "SetNode"}:
                    return input_value(node, 0)
                if kind == "GetNode":
                    setters = [
                        item
                        for item in nodes.values()
                        if item.get("type") == "SetNode" and constant(item) == constant(node)
                    ]
                    if len(setters) != 1:
                        raise ValueError(
                            f"GetNode {prefix}{node_id} requires exactly one matching SetNode"
                        )
                    return input_value(setters[0], 0)
                if kind in UNPACK_TYPES:
                    props = node.get("properties", {})
                    channel = props.get("terry_wireless_bus_channel")
                    packs = []
                    wire = links.get(str((node.get("inputs") or [{}])[0].get("link")))
                    if wire and wire[0] in nodes:
                        packs = [nodes[wire[0]]]
                    elif kind == "TerryXuWirelessBusUnpack":
                        packs = [
                            item
                            for item in nodes.values()
                            if item.get("type") in PACK_TYPES
                            and channel
                            and item.get("properties", {}).get("terry_wireless_bus_channel")
                            == channel
                        ]
                    if len(packs) != 1:
                        raise ValueError(f"Bus {prefix}{node_id} requires exactly one input bus")
                    pack = packs[0]
                    lanes = pack.get("properties", {}).get("terry_wire_bus_lanes", [])
                    ids = props.get("terry_wire_bus_lane_ids", [])
                    outputs = node.get("outputs", [])
                    lane_id = outputs[slot].get("terry_lane_id") if slot < len(outputs) else None
                    lane_id = lane_id or (ids[slot] if slot < len(ids) else None)
                    lane = (
                        next(
                            (i for i, value in enumerate(lanes) if value.get("id") == lane_id), None
                        )
                        if lane_id
                        else slot
                    )
                    return input_value(pack, lane) if lane is not None else MISSING
                return [f"{prefix}{node_id}", slot]
            finally:
                visiting.remove(key)

        for node_id, node in nodes.items():
            kind = node.get("type")
            if kind in definitions:
                if node.get("mode", 0) not in (2, 4):
                    resolve(node_id, 0)
                continue
            if node.get("mode", 0) in (2, 4) or kind in VIRTUAL_TYPES:
                continue
            inputs = dict(widgets[node_id])
            for index, spec in enumerate(node.get("inputs", [])):
                if spec.get("link") is not None:
                    value = input_value(node, index)
                    if value is MISSING:
                        inputs.pop(spec.get("name"), None)
                    else:
                        inputs[spec["name"]] = value
            prompt[f"{prefix}{node_id}"] = {"class_type": kind, "inputs": inputs}
        return {
            target_slot: resolve(origin, slot)
            for origin, slot, target, target_slot in links.values()
            if target == output_id
        }

    scope(raw, "", [], ())
    return prompt


def prune_to_outputs(prompt: dict, output_types: set[str]) -> dict:
    pending = [key for key, node in prompt.items() if node.get("class_type") in output_types]
    retained = set()
    while pending:
        key = pending.pop()
        if key in retained or key not in prompt:
            continue
        retained.add(key)
        for value in prompt[key].get("inputs", {}).values():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[1], int)
                and str(value[0]) in prompt
            ):
                pending.append(str(value[0]))
    return {key: node for key, node in prompt.items() if key in retained}
