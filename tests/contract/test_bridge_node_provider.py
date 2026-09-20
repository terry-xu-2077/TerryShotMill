from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SOURCE = Path(os.environ.get(
    "SHOTMILL_BRIDGE_NODES",
    str(Path(__file__).resolve().parents[2] / "integrations/comfyui_shotmill/nodes.py"),
))
spec = importlib.util.spec_from_file_location("shotmill_bridge_nodes", SOURCE)
assert spec is not None and spec.loader is not None
bridge_nodes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge_nodes)


def test_sparse_bridge_outputs_keep_declared_socket_indices():
    node = bridge_nodes.ShotMillIOBridgeIn()
    first, second = object(), object()
    outputs = node.bridge(**{"*": first, "* 2": second})
    assert len(outputs) == len(node.RETURN_TYPES)
    assert outputs[:2] == (first, second)
    assert all(value is None for value in outputs[2:])
    assert outputs[8] is None  # The reported workflow still connects ref_image_8.


def test_missing_first_and_middle_inputs_never_shift_references():
    node = bridge_nodes.ShotMillIOBridgeIn()
    later, last = object(), object()
    outputs = node.bridge(**{"* 10": last, "* 3": later})
    assert outputs[:3] == (None, None, later)
    assert outputs[9] is last
    assert len(outputs) == len(node.RETURN_TYPES)


@pytest.mark.parametrize("node_class", [
    bridge_nodes.ShotMillIOBridgeIn, bridge_nodes.ShotMillIOBridgeOut,
])
@pytest.mark.parametrize("value", [
    ["single list item"], (("nested tuple",),),
    {"waveform": [[1, 2]], "sample_rate": 48000}, "text", [],
])
def test_bridge_preserves_values_without_unwrapping(node_class, value):
    assert node_class().bridge(**{"*": value})[0] is value


def test_dynamic_input_schema_accepts_sparse_and_literal_ports():
    schema = bridge_nodes.ShotMillIOBridgeIn.INPUT_TYPES()
    assert not schema.get("required")
    assert len(schema["optional"]) == 256
    for name in ("*", "* 2", "* 10", "* 256"):
        assert schema["optional"][name][0] == "*"
        assert not schema["optional"][name][1].get("rawLink", False)


def test_empty_bridge_still_returns_all_declared_outputs():
    node = bridge_nodes.ShotMillIOBridgeIn()
    assert node.bridge() == (None,) * len(node.RETURN_TYPES)
