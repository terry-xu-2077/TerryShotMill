import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def compile_canvas():
    path = Path(__file__).parents[2] / "integrations/comfyui_shotmill/canvas_compiler.py"
    spec = importlib.util.spec_from_file_location("canvas_compiler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compile_canvas


def test_compiler_ignores_notes_and_resolves_bypass_and_named_widgets(compile_canvas):
    raw = {
        "nodes": [
            {"id": 1, "type": "Source"},
            {
                "id": 2,
                "type": "Patch",
                "mode": 4,
                "inputs": [{"name": "model", "type": "MODEL", "link": 1}],
                "outputs": [{"type": "MODEL"}],
            },
            {
                "id": 3,
                "type": "Sink",
                "inputs": [
                    {"name": "model", "link": 2},
                    {"name": "steps", "widget": {"name": "steps"}, "link": 3},
                    {"name": "denoise", "widget": {"name": "denoise"}},
                ],
                "widgets_values": [8, 1.0],
            },
            {"id": 4, "type": "MarkdownNote"},
            {"id": 5, "type": "PrimitiveInt", "widgets_values_named": {"value": 8}},
        ],
        "links": [[1, 1, 0, 2, 0, "MODEL"], [2, 2, 0, 3, 0, "MODEL"], [3, 5, 0, 3, 1, "INT"]],
    }
    prompt = compile_canvas(raw)
    assert "2" not in prompt and "4" not in prompt
    assert prompt["3"]["inputs"] == {"model": ["1", 0], "steps": ["5", 0], "denoise": 1.0}


def test_compiler_expands_subgraph_and_keeps_parent_widget_override(compile_canvas):
    raw = {
        "nodes": [
            {"id": 1, "type": "Source"},
            {
                "id": 2,
                "type": "group-a",
                "inputs": [
                    {"name": "", "link": 1},
                    {"name": "amount", "widget": {"name": "amount"}},
                ],
                "widgets_values_named": {"amount": 8},
            },
            {"id": 3, "type": "Sink", "inputs": [{"name": "model", "link": 2}]},
        ],
        "links": [[1, 1, 0, 2, 0, "MODEL"], [2, 2, 0, 3, 0, "MODEL"]],
        "definitions": {
            "subgraphs": [
                {
                    "id": "group-a",
                    "inputNode": {"id": -10},
                    "outputNode": {"id": -20},
                    "nodes": [
                        {
                            "id": 5,
                            "type": "Patch",
                            "inputs": [
                                {"name": "model", "link": 10},
                                {"name": "amount", "link": 11},
                            ],
                        }
                    ],
                    "links": [
                        {
                            "id": 10,
                            "origin_id": -10,
                            "origin_slot": 0,
                            "target_id": 5,
                            "target_slot": 0,
                        },
                        {
                            "id": 11,
                            "origin_id": -10,
                            "origin_slot": 1,
                            "target_id": 5,
                            "target_slot": 1,
                        },
                        {
                            "id": 12,
                            "origin_id": 5,
                            "origin_slot": 0,
                            "target_id": -20,
                            "target_slot": 0,
                        },
                    ],
                }
            ]
        },
    }
    prompt = compile_canvas(raw)
    assert prompt["2:5"]["inputs"] == {"model": ["1", 0], "amount": 8}
    assert prompt["3"]["inputs"]["model"] == ["2:5", 0]
    assert "2" not in prompt


def test_compiler_resolves_wireless_bus_lane_identity_and_get_node(compile_canvas):
    raw = {
        "nodes": [
            {"id": 1, "type": "Source"},
            {
                "id": 2,
                "type": "SetNode",
                "widgets_values": ["model"],
                "inputs": [{"name": "value", "link": 1}],
            },
            {"id": 3, "type": "GetNode", "widgets_values": ["model"]},
            {
                "id": 4,
                "type": "TerryXuWirelessBusPack",
                "inputs": [{"name": "model", "link": 2}],
                "properties": {
                    "terry_wireless_bus_channel": "a",
                    "terry_wire_bus_lanes": [{"id": "model"}],
                },
            },
            {
                "id": 5,
                "type": "TerryXuWirelessBusUnpack",
                "outputs": [{}, {}],
                "properties": {
                    "terry_wireless_bus_channel": "a",
                    "terry_wire_bus_lane_ids": ["other", "model"],
                },
            },
            {"id": 6, "type": "Sink", "inputs": [{"name": "model", "link": 3}]},
        ],
        "links": [[1, 1, 0, 2, 0, "MODEL"], [2, 3, 0, 4, 0, "MODEL"], [3, 5, 1, 6, 0, "MODEL"]],
    }
    prompt = compile_canvas(raw)
    assert prompt["6"]["inputs"]["model"] == ["1", 0]
    assert set(prompt) == {"1", "6"}
