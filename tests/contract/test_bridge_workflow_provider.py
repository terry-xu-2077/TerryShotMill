from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from shotmill.domain.providers import ResolvedMedia, VideoGenerationRequest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


def test_bridge_validation_error_preserves_node_details():
    def handler(request):
        if request.url.path.endswith("/workflows"):
            return httpx.Response(200, json={"workflows": [{"id": "w.json", "inputs": []}]})
        return httpx.Response(
            400,
            json={
                "error": {"message": "Prompt validation failed"},
                "nodeErrors": {
                    "42": {"errors": [{"message": "Required input missing", "details": "model"}]}
                },
            },
        )

    provider = ComfyUIVideoGenerationProvider(
        "http://bridge",
        Path("w.json"),
        transport=httpx.MockTransport(handler),
    )
    request = VideoGenerationRequest(
        job_id="j",
        project_id="p",
        task_id="t",
        final_prompt="test",
        assets=(),
        params={},
    )
    with pytest.raises(ShotMillError) as caught:
        asyncio.run(provider.generate(request))
    assert caught.value.code == "SHOTMILL_BRIDGE_SUBMISSION_REJECTED"
    assert "42" in str(caught.value)
    assert "model" in str(caught.value)


@pytest.fixture
def bridge_graph():
    # Exercise the production graph helpers without importing the GPU server.
    path = Path(__file__).parents[2] / "integrations/comfyui_shotmill/bridge_api.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {
        "INPUT_LOADERS",
        "BUS_PACK_TYPES",
        "BUS_UNPACK_TYPES",
        "BUS_TYPE",
        "BRIDGE_IN_TYPES",
        "BRIDGE_OUT_TYPES",
        "LEGACY_BRIDGE_TYPES",
    }
    tree.body = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        or isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        or isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)
    ]
    compiler_spec = importlib.util.spec_from_file_location(
        "canvas_compiler", path.with_name("canvas_compiler.py")
    )
    compiler = importlib.util.module_from_spec(compiler_spec)
    compiler_spec.loader.exec_module(compiler)
    scope = {"Any": Any, "compile_canvas": compiler.compile_canvas}
    exec(compile(tree, str(path), "exec"), scope)
    return scope


@pytest.mark.parametrize("expected", ["queued", "running", "not_found", "completed", "failed"])
def test_bridge_job_status_uses_live_queue_and_history(bridge_graph, expected):
    events = []
    queue_item = (1, "prompt-1", {}, {}, [], {})

    def current_queue():
        events.append("queue")
        return (
            [queue_item] if expected == "running" else [],
            [queue_item] if expected == "queued" else [],
        )

    def history(**_kwargs):
        events.append("history")
        if expected in {"completed", "failed"}:
            return {
                "prompt-1": {
                    "outputs": {},
                    "status": {
                        "status_str": "error" if expected == "failed" else "success",
                        "messages": [["execution_error", {"exception_message": "test failure"}]],
                    },
                }
            }
        return {}

    bridge_graph.update(
        {
            "JOB_INDEX": "unused",
            "_load_index": lambda _: {"jobs": {"job-1": {"promptId": "prompt-1"}}},
            "_save_index": lambda *_args: None,
            "PromptServer": SimpleNamespace(
                instance=SimpleNamespace(
                    prompt_queue=SimpleNamespace(
                        get_current_queue=current_queue,
                        get_history=history,
                    )
                )
            ),
        }
    )
    state = bridge_graph["_job_state"]("job-1")
    assert state["status"] == expected
    # Read history after the queue snapshot, so a completion between reads is not lost.
    assert events == ["queue", "history"]
    if expected == "failed":
        assert "test failure" in str(state["error"])


@pytest.mark.parametrize(("state", "http_status"), [("failed", 200), ("not_found", 404)])
def test_bridge_failed_job_is_not_a_missing_http_resource(bridge_graph, state, http_status):
    bridge_graph.update(
        {
            "_safe_name": lambda name, _: name,
            "_job_state": lambda _: {"ok": False, "status": state},
            "web": SimpleNamespace(json_response=lambda data, status: (data, status)),
        }
    )
    _, response_status = asyncio.run(
        bridge_graph["_job"](SimpleNamespace(match_info={"job_id": "job-1"}))
    )
    assert response_status == http_status


@pytest.mark.parametrize("terminal", ["completed", "failed"])
def test_bridge_keeps_terminal_state_when_comfy_history_is_cleared(
    bridge_graph, terminal, tmp_path
):
    index = {"jobs": {"job-1": {"promptId": "prompt-1", "workflowId": "w.json"}}}
    index_path = tmp_path / "jobs.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    saved = []
    save_index = bridge_graph["_save_index"]

    def persist(path, value):
        saved.append(True)
        save_index(path, value)

    history = {
        "prompt-1": {
            "outputs": {
                "save": {
                    "images": [
                        {
                            "filename": "result_00001.png",
                            "subfolder": "shotmill/results/job-1",
                            "type": "output",
                        }
                    ]
                }
            },
            "status": {"status_str": "error" if terminal == "failed" else "success"},
        }
    }
    bridge_graph.update(
        {
            "JOB_INDEX": index_path,
            "json": json,
            "_save_index": persist,
            "PromptServer": SimpleNamespace(
                instance=SimpleNamespace(
                    prompt_queue=SimpleNamespace(
                        get_current_queue=lambda: ([], []),
                        get_history=lambda **_kwargs: history,
                    )
                )
            ),
        }
    )
    first = bridge_graph["_job_state"]("job-1")
    history.clear()
    restored = bridge_graph["_job_state"]("job-1")
    assert restored == first
    assert restored["status"] == terminal
    assert saved == [True]
    restored_index = json.loads(index_path.read_text(encoding="utf-8"))
    assert restored_index["jobs"]["job-1"]["workflowId"] == "w.json"
    assert restored_index["jobs"]["job-1"]["terminalState"] == first
    assert not index_path.with_name("jobs.json.tmp").exists()
    if terminal == "completed":
        assert restored["results"][0]["filename"] == "result_00001.png"


def workflow():
    return {
        "nodes": [
            {"id": 1, "type": "LoadImage", "outputs": [{"type": "IMAGE"}]},
            {
                "id": 2,
                "type": "ShotMillIOBridgeIn",
                "inputs": [
                    {"name": "*", "link": 1},
                    {"name": "* 2", "link": None},
                ],
            },
            {
                "id": 3,
                "type": "ArbitraryGenerator",
                "inputs": [
                    {"name": "image_0", "type": "IMAGE", "link": 2},
                ],
            },
        ],
        "links": [[1, 1, 0, 2, 0, "IMAGE"], [2, 2, 0, 3, 0, "IMAGE"]],
    }


def test_bridge_catalog_ignores_empty_extension_and_preserves_zero_slot(bridge_graph):
    inputs, _ = bridge_graph["_bridge_ports"](workflow())
    assert len(inputs) == 1
    assert inputs[0]["targetPort"] == "image_0"
    assert inputs[0]["targetNodeId"] == "3"
    assert inputs[0]["targetSlot"] == "0"


def test_bridge_binding_empty_slot_does_not_use_workflow_sample(bridge_graph):
    raw = workflow()
    raw["nodes"][0]["widgets_values_named"] = {"image": "sample.png"}
    prompt = bridge_graph["_canvas_prompt"](raw)
    bridge_graph["_bind_input_markers"](prompt, {"assets": [], "inputSlots": [None]}, raw)
    assert "image_0" not in prompt["3"]["inputs"]


def test_bridge_binding_reactivates_bypassed_loader_and_binds_final_port(bridge_graph):
    raw = workflow()
    raw["nodes"][0]["mode"] = 4
    prompt = bridge_graph["_canvas_prompt"](raw)
    bridge_graph["_bind_input_markers"](
        prompt,
        {
            "assets": [{"reference": "<Picture 1>", "mediaType": "image"}],
            "assetValues": {"<Picture 1>": "shotmill/assets/selected.png"},
        },
        raw,
    )
    assert prompt["1"]["inputs"]["image"] == "shotmill/assets/selected.png"
    assert prompt["3"]["inputs"]["image_0"] == ["1", 0]


def test_h3_sparse_reference_labels_follow_present_input_order(bridge_graph):
    prompt = {
        "9": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "prompt": "<Subject 1> uses <Picture 3> then <Picture 7>; "
                "<Video 2> and <Audio 3> / <Audio 1>"
            },
        }
    }

    def record(name, reference):
        return ({"targets": [{"targetNodeId": "9", "name": name}]}, {"reference": reference})

    bridge_graph["_adapt_h3_reference_labels"](
        prompt,
        [
            record("ref_images.ref_image_6", "<Picture 7>"),
            record("ref_audios.ref_audio_0", "<Audio 1>"),
            record("ref_images.ref_image_2", "<Picture 3>"),
            record("ref_videos.ref_video_1", "<Video 2>"),
            record("ref_video_audios.ref_video_audio_1", "<Audio 3>"),
        ],
    )
    assert (
        prompt["9"]["inputs"]["prompt"]
        == "<Subject 1> uses <Picture 1> then <Picture 2>; <Video 1> and <Audio 1> / <Audio 2>"
    )


def test_other_generators_keep_reference_labels(bridge_graph):
    prompt = {"9": {"class_type": "OtherGenerator", "inputs": {"prompt": "<Picture 3>"}}}
    bridge_graph["_adapt_h3_reference_labels"](
        prompt,
        [
            (
                {"targets": [{"targetNodeId": "9", "name": "ref_image_2"}]},
                {"reference": "<Picture 3>"},
            ),
        ],
    )
    assert prompt["9"]["inputs"]["prompt"] == "<Picture 3>"


def test_h3_rejects_reference_to_empty_slot_instead_of_reusing_compacted_number(bridge_graph):
    prompt = {
        "9": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {"prompt": "<Picture 1> and <Picture 3>"},
        }
    }
    with pytest.raises(ValueError, match="empty input slots"):
        bridge_graph["_adapt_h3_reference_labels"](
            prompt,
            [
                (
                    {"targets": [{"targetNodeId": "9", "name": "ref_image_2"}]},
                    {"reference": "<Picture 3>"},
                ),
            ],
        )


def test_video_provider_keeps_optional_holes_and_port_identity(tmp_path):
    ports = [
        {
            "name": f"image{i}",
            "type": "IMAGE",
            "targetNodeId": "9",
            "targetPort": f"ref_image_{i}",
            "sourceNodeId": str(i),
        }
        for i in range(3)
    ]
    media = ResolvedMedia(
        asset_id="a",
        reference="<Picture 3>",
        role="reference",
        media_type="image",
        path=tmp_path / "a.png",
    )
    request = VideoGenerationRequest(
        job_id="j",
        project_id="p",
        task_id="t",
        final_prompt="<Picture 3>",
        assets=(media,),
        params={
            "workflowInputs": {
                "workflowId": "w.json",
                "slots": [
                    {"portId": "9:ref_image_0:0", "assetId": None, "reference": "<Picture 1>"},
                    {"portId": "9:ref_image_2:2", "assetId": "a", "reference": "<Picture 3>"},
                ],
            },
        },
    )
    provider = ComfyUIVideoGenerationProvider("http://bridge", None)

    async def validate():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"workflows": [{"id": "w.json", "inputs": ports}]}
                )
            )
        ) as client:
            return await provider._validate_workflow_inputs(
                client, "http://bridge", "w.json", request
            )

    assert asyncio.run(validate()) == [
        None,
        None,
        {"reference": "<Picture 3>", "mediaType": "image"},
    ]


def test_bridge_catalog_traces_wireless_bus_to_final_receiver(bridge_graph):
    raw = workflow()
    raw["nodes"].extend(
        [
            {
                "id": 4,
                "type": "TerryXuWirelessBusPack",
                "inputs": [
                    {"name": "image", "link": 2},
                ],
                "properties": {
                    "terry_wireless_bus_channel": "refs",
                    "terry_wire_bus_lanes": [{"id": "lane-a"}],
                },
            },
            {
                "id": 5,
                "type": "TerryXuWirelessBusUnpack",
                "inputs": [],
                "outputs": [{"name": "image", "terry_lane_id": "lane-a"}],
                "properties": {"terry_wireless_bus_channel": "refs"},
            },
        ]
    )
    raw["links"][1] = [2, 2, 0, 4, 0, "IMAGE"]
    raw["links"].append([3, 5, 0, 3, 0, "IMAGE"])
    inputs, _ = bridge_graph["_bridge_ports"](raw)
    assert inputs[0]["targetNodeId"] == "3"
    assert inputs[0]["targetPort"] == "image_0"


def test_bridge_catalog_preserves_sparse_input_output_pairing(bridge_graph):
    raw = workflow()
    raw["nodes"][1]["inputs"] = [
        {"name": "*", "link": None},
        {"name": "* 2", "link": 1},
        {"name": "* 3", "link": None},
    ]
    raw["links"] = [[1, 1, 0, 2, 1, "IMAGE"], [2, 2, 1, 3, 0, "IMAGE"]]
    inputs, _ = bridge_graph["_bridge_ports"](raw)
    assert len(inputs) == 1
    assert inputs[0]["targetPort"] == "image_0"


def test_bridge_graph_cycles_do_not_recurse_forever(bridge_graph):
    raw = workflow()
    raw["nodes"].append(
        {
            "id": 4,
            "type": "ShotMillIOBridgeIn",
            "inputs": [
                {"name": "*", "link": 2},
            ],
        }
    )
    raw["links"][1] = [2, 2, 0, 4, 0, "IMAGE"]
    raw["links"].append([3, 4, 0, 2, 0, "IMAGE"])
    consumers = bridge_graph["_all_consumers"](raw, raw["nodes"])
    assert bridge_graph["_final_targets"](raw, raw["nodes"], consumers, "2", 0) == []


def test_bridge_catalog_uses_bus_lane_ids_after_output_reorder(bridge_graph):
    raw = workflow()
    raw["nodes"].extend(
        [
            {
                "id": 4,
                "type": "TerryXuWireBusPack",
                "inputs": [
                    {"name": "image", "link": 2},
                ],
                "properties": {"terry_wire_bus_lanes": [{"id": "lane-a"}]},
            },
            {
                "id": 5,
                "type": "TerryXuWireBusUnpack",
                "inputs": [
                    {"name": "bus", "link": 3},
                ],
                "outputs": [
                    {"name": "unused", "terry_lane_id": "lane-b"},
                    {"name": "image", "terry_lane_id": "lane-a"},
                ],
            },
        ]
    )
    raw["links"][1] = [2, 2, 0, 4, 0, "IMAGE"]
    raw["links"].extend(
        [
            [3, 4, 0, 5, 0, "TERRY_WIRE_BUS"],
            [4, 5, 1, 3, 0, "IMAGE"],
        ]
    )
    inputs, _ = bridge_graph["_bridge_ports"](raw)
    assert inputs[0]["targetNodeId"] == "3"
    assert inputs[0]["targetPort"] == "image_0"


def test_bridge_catalog_handles_multiple_markers_without_h3_names(bridge_graph):
    raw = workflow()
    raw["nodes"].extend(
        [
            {"id": 4, "type": "PrimitiveString", "outputs": [{"type": "STRING"}]},
            {"id": 5, "type": "ShotMillIOBridgeIn", "inputs": [{"name": "*", "link": 3}]},
        ]
    )
    raw["nodes"][2]["inputs"].append({"name": "caption", "type": "STRING", "link": 4})
    raw["links"].extend([[3, 4, 0, 5, 0, "STRING"], [4, 5, 0, 3, 1, "STRING"]])
    inputs, _ = bridge_graph["_bridge_ports"](raw)
    assert [(port["sourceNodeId"], port["targetPort"]) for port in inputs] == [
        ("1", "image_0"),
        ("4", "caption"),
    ]
