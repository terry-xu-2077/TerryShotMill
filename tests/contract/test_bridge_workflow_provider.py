from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import json
import math
import re
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from shotmill.domain.providers import ResolvedMedia, VideoGenerationRequest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


def test_context_video_fills_compatible_free_port_without_changing_explicit_assets(tmp_path):
    ports = [
        {"type": "IMAGE", "targetNodeId": "h3", "targetPort": "ref_image_0", "sourceNodeId": "a"},
        {"type": "IMAGE", "targetNodeId": "h3", "targetPort": "ref_image_1", "sourceNodeId": "b"},
        {"type": "VIDEO", "targetNodeId": "decode", "targetPort": "video", "sourceNodeId": "c"},
    ]

    def handler(_request):
        return httpx.Response(200, json={"workflows": [{"id": "w.json", "inputs": ports}]})

    provider = ComfyUIVideoGenerationProvider("http://bridge", Path("w.json"))
    request = VideoGenerationRequest(
        "j",
        "p",
        "t",
        "detailed_description:\nContinue",
        (
            ResolvedMedia("a", "<Picture 1>", None, "image", tmp_path / "a.png"),
            ResolvedMedia("context-a", "<Video 1>", "context_segment", "video", tmp_path / "b.mp4"),
        ),
        {
            "workflowInputs": {
                "workflowId": "w.json",
                "slots": [
                    {"portId": "h3:ref_image_0:a", "assetId": "a", "reference": "<Picture 1>"}
                ],
            }
        },
    )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await provider._validate_workflow_inputs(
                client, "http://bridge", "w.json", request
            )

    assert asyncio.run(check()) == [
        {"reference": "<Picture 1>", "mediaType": "image"},
        None,
        {"reference": "<Video 1>", "mediaType": "video"},
    ]


def test_h3_video_reference_through_native_decoder_is_recognized(bridge_graph):
    prompt = {
        "decode": {"class_type": "GetVideoComponents", "inputs": {"video": ["load", 0]}},
        "h3": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "ref_videos.ref_video_0": ["decode", 0],
                "prompt": "Continue the ending of <Video 2>.",
            },
        },
    }
    bridge_graph["_adapt_h3_reference_labels"](
        prompt,
        [
            (
                {"targets": [{"targetNodeId": "decode", "name": "video"}]},
                {"reference": "<Video 2>", "mediaType": "video"},
            )
        ],
    )
    assert prompt["h3"]["inputs"]["prompt"] == "Continue the ending of <Video 1>."


def test_bridge_validation_error_preserves_node_details(bridge_snapshot):
    def handler(request):
        if request.url.path.endswith("/workflows/validate"):
            return httpx.Response(200, json={"ok": True})
        if request.url.path.endswith("/workflows/snapshot"):
            return httpx.Response(200, json={"snapshot": bridge_snapshot()})
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
    scope = {
        "Any": Any,
        "compile_canvas": compiler.compile_canvas,
        "math": math,
        "hashlib": hashlib,
        "json": json,
        "Path": Path,
    }
    exec(compile(tree, str(path), "exec"), scope)
    return scope


def test_bridge_frozen_graph_survives_deleted_workflow_and_submission(
    bridge_graph,
    tmp_path,
    monkeypatch,
):
    raw = {
        "prompt": {
            "1": {"class_type": "PrimitiveInt", "inputs": {"value": 17}},
            "2": {"class_type": "ShotMillIOBridgeIn", "inputs": {"*": ["1", 0]}},
            "3": {"class_type": "TestOutput", "inputs": {"frames": ["2", 0]}},
        }
    }
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    bridge_graph["WORKFLOW_ROOT"] = tmp_path
    snapshot = bridge_graph["_capture_workflow"]("frozen.json")
    assert snapshot["inputs"][0]["type"] == "INT"
    path.unlink()
    # Restore an independent execution copy, including metadata used by binding.
    prompt, restored_raw = bridge_graph["_restore_workflow"](snapshot, "frozen.json")
    assert restored_raw == raw
    prompt["1"]["inputs"]["value"] = 999
    assert snapshot["prompt"]["1"]["inputs"]["value"] == 17
    queued = []

    async def validate(_id, execution_prompt, _partial):
        assert execution_prompt["1"]["inputs"]["value"] == 17
        assert execution_prompt["3"]["inputs"]["frames"] == ["1", 0]
        return True, None, ["3"], {}

    from types import ModuleType

    nodes = ModuleType("nodes")
    nodes.NODE_CLASS_MAPPINGS = {
        "TestOutput": type(
            "Output",
            (),
            {
                "OUTPUT_NODE": True,
                "INPUT_TYPES": classmethod(lambda cls: {}),
            },
        )
    }
    monkeypatch.setitem(sys.modules, "nodes", nodes)
    compiler_spec = importlib.util.spec_from_file_location(
        "snapshot_compiler",
        Path(__file__).parents[2] / "integrations/comfyui_shotmill/canvas_compiler.py",
    )
    compiler = importlib.util.module_from_spec(compiler_spec)
    compiler_spec.loader.exec_module(compiler)
    bridge_graph.update(
        {
            "re": re,
            "uuid": uuid,
            "time": time,
            "NATIVE_SAVE_NODES": set(),
            "JOB_INDEX": tmp_path / "jobs.json",
            "prune_to_outputs": compiler.prune_to_outputs,
            "execution": SimpleNamespace(validate_prompt=validate),
            "PromptServer": SimpleNamespace(
                instance=SimpleNamespace(
                    number=0,
                    node_replace_manager=SimpleNamespace(apply_replacements=lambda _: None),
                    prompt_queue=SimpleNamespace(put=queued.append),
                )
            ),
            "web": SimpleNamespace(json_response=lambda body, status=200: (status, body)),
        }
    )

    async def request_json():
        return {"jobId": "frozen-job", "workflowId": "frozen.json", "workflowSnapshot": snapshot}

    preflight = asyncio.run(bridge_graph["_validate_workflow"](SimpleNamespace(json=request_json)))
    assert preflight[0] == 200, preflight
    assert preflight[1]["ok"] is True
    assert queued == []
    assert not (tmp_path / "jobs.json").exists()
    response = asyncio.run(bridge_graph["_create_job"](SimpleNamespace(json=request_json)))
    assert response[0] == 200, response
    assert len(queued) == 1
    assert snapshot["prompt"]["3"]["inputs"]["frames"] == ["2", 0]


@pytest.mark.parametrize("damage", ["digest", "workflow", "version", "prompt"])
def test_bridge_rejects_damaged_snapshot_before_loading_or_queuing(
    bridge_graph,
    bridge_snapshot,
    damage,
):
    snapshot = bridge_snapshot()
    if damage == "digest":
        snapshot["raw"]["prompt"]["1"]["inputs"]["value"] = 999
    elif damage == "workflow":
        snapshot["workflowId"] = "other.json"
    elif damage == "version":
        snapshot["version"] = 999
    else:
        snapshot["prompt"] = {}
    with pytest.raises(ValueError):
        bridge_graph["_restore_workflow"](snapshot, "w.json")


def test_legacy_or_incomplete_video_snapshot_cannot_reload_current_file(bridge_snapshot):
    def unexpected_request(request):
        pytest.fail(f"Old queued jobs must not silently capture today's workflow: {request.url}")

    provider = ComfyUIVideoGenerationProvider(
        "http://bridge",
        Path("w.json"),
        transport=httpx.MockTransport(unexpected_request),
    )
    request = VideoGenerationRequest("j", "p", "t", "test", (), {})
    profile = provider.capture_profile(request)
    with pytest.raises(ShotMillError, match="快照"):
        asyncio.run(provider.bind_profile(profile).generate(request))
    profile["version"] = 1
    with pytest.raises(ShotMillError, match="旧视频任务"):
        provider.bind_profile(profile)


@pytest.mark.parametrize("failure", [None, "model", "cycle", "loop", "missing_node"])
def test_preflight_defers_only_bound_media_and_keeps_native_graph_validation(
    bridge_graph,
    monkeypatch,
    failure,
):
    from types import ModuleType

    class V3:
        pass

    class Image:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"image": (["saved.png"],)}}

    class Output:
        OUTPUT_NODE = True

    class LoopError(Exception):
        error = {"type": "invalid_loop", "extra_info": {"node_ids": ["out"]}}

    prompt = {
        "bound": {"class_type": "LoadImage", "inputs": {"image": "pending-upload"}},
        "saved": {"class_type": "LoadImage", "inputs": {"image": "saved.png"}},
        "out": {"class_type": "Output", "inputs": {"image": ["bound", 0]}},
    }
    if failure == "missing_node":
        prompt["out"]["class_type"] = "MissingOutput"
    nodes = ModuleType("nodes")
    nodes.NODE_CLASS_MAPPINGS = {"LoadImage": Image, "Output": Output}
    monkeypatch.setitem(sys.modules, "nodes", nodes)
    calls = []

    async def validate(_id, graph, node_id, cache):
        assert graph is prompt
        assert node_id == "out"
        assert cache == {"bound": (True, [], "bound")}
        assert "saved" not in cache  # A workflow's own file still needs native validation.
        calls.append("inputs")
        reasons = [{"type": "dependency_cycle" if failure == "cycle" else "value_not_in_list"}]
        cache[node_id] = (
            (False, reasons, node_id) if failure in {"model", "cycle"} else (True, [], node_id)
        )

    def loops(*_args):
        calls.append("loops")
        if failure == "loop":
            raise LoopError()

    bridge_graph.update(
        {
            "uuid": uuid,
            "execution": SimpleNamespace(
                _ComfyNodeInternal=V3,
                validate_inputs=validate,
                validate_loops=loops,
                LoopValidationError=LoopError,
            ),
        }
    )
    result = asyncio.run(bridge_graph["_validate_preflight"](prompt, {"bound": "image"}))
    assert result[0] is (failure is None)
    if failure == "missing_node":
        assert result[1]["nodeId"] == "out"
        assert calls == []
    else:
        assert calls == (["inputs"] if failure == "cycle" else ["inputs", "loops"])
        if failure:
            assert result[3]["out"]["errors"]


def test_preflight_cannot_skip_extra_media_loader_parameters(bridge_graph, monkeypatch):
    from types import ModuleType

    class ChangedLoader:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"image": ([],), "new_required_parameter": ("INT",)}}

    nodes = ModuleType("nodes")
    nodes.NODE_CLASS_MAPPINGS = {"LoadImage": ChangedLoader}
    monkeypatch.setitem(sys.modules, "nodes", nodes)
    bridge_graph.update(
        {
            "uuid": uuid,
            "execution": SimpleNamespace(_ComfyNodeInternal=type("V3", (), {})),
        }
    )
    with pytest.raises(ValueError, match="Cannot defer"):
        asyncio.run(
            bridge_graph["_validate_preflight"](
                {"1": {"class_type": "LoadImage", "inputs": {"image": "pending"}}},
                {"1": "image"},
            )
        )


@pytest.mark.parametrize("codec,valid", [("h264", True), ("typo", False)])
def test_nested_dynamic_choices_are_checked_before_native_schema_expansion(
    bridge_graph,
    codec,
    valid,
):
    schema = {
        "required": {
            "format": (
                "COMFY_DYNAMICCOMBO_V3",
                {
                    "options": [
                        {
                            "key": "mp4",
                            "inputs": {
                                "required": {
                                    "codec": (
                                        "COMFY_DYNAMICCOMBO_V3",
                                        {"options": [{"key": "h264", "inputs": {}}]},
                                    ),
                                }
                            },
                        }
                    ]
                },
            )
        }
    }
    values = {"format": "mp4", "format.codec": codec}
    if valid:
        bridge_graph["_check_dynamic_choices"]("42", schema, values)
    else:
        with pytest.raises(ValueError, match="Node 42 input format.codec: value_not_in_list"):
            bridge_graph["_check_dynamic_choices"]("42", schema, values)


def test_wildcard_socket_is_not_mistaken_for_dynamic_combo(bridge_graph):
    class AnySocket(str):
        def __eq__(self, _other):
            return True

    bridge_graph["_check_dynamic_choices"](
        "bridge",
        {"required": {"value": (AnySocket("*"), {})}},
        {"value": ["loader", 0]},
    )


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


def test_empty_optional_video_disconnects_h3_decoder_chain(bridge_graph):
    raw = workflow()
    raw["nodes"][0].update(type="LoadVideo", outputs=[{"type": "VIDEO"}])
    raw["nodes"][2].update(
        type="GetVideoComponents", inputs=[{"name": "video", "type": "VIDEO", "link": 2}]
    )
    raw["nodes"].append(
        {
            "id": 4,
            "type": "MiniMaxH3ReferenceToVideo",
            "inputs": [{"name": "ref_videos.ref_video_0", "type": "IMAGE", "link": 3}],
        }
    )
    raw["links"].append([3, 3, 0, 4, 0, "IMAGE"])
    prompt = bridge_graph["_canvas_prompt"](raw)
    bridge_graph["_bind_input_markers"](prompt, {"assets": [], "inputSlots": [None]}, raw)
    assert "ref_videos.ref_video_0" not in prompt["4"]["inputs"]


def test_input_video_preview_is_not_a_generated_result(bridge_graph):
    entry = {
        "outputs": {
            "load": {"images": [{"filename": "reference.mp4", "type": "input"}]},
            "preview": {"images": [{"filename": "preview.png", "type": "temp"}]},
            "save": {"images": [{"filename": "generated.mp4", "type": "output"}]},
        }
    }
    results = bridge_graph["_history_results"](entry)
    assert [item["filename"] for item in results] == ["generated.mp4"]


def test_old_cached_result_list_excludes_input_previews(bridge_graph):
    cached = {
        "status": "completed",
        "results": [
            {"filename": "reference.mp4", "type": "input"},
            {"filename": "generated.mp4", "type": "output"},
        ],
    }
    bridge_graph.update(
        JOB_INDEX="unused", _load_index=lambda _: {"jobs": {"j": {"terminalState": cached}}}
    )
    state = bridge_graph["_job_state"]("j")
    assert [item["filename"] for item in state["results"]] == ["generated.mp4"]
    assert len(cached["results"]) == 2


def test_bridge_catalog_ignores_empty_extension_and_preserves_zero_slot(bridge_graph):
    inputs, _ = bridge_graph["_bridge_ports"](workflow())
    assert len(inputs) == 1
    assert inputs[0]["targetPort"] == "image_0"
    assert inputs[0]["targetNodeId"] == "3"
    assert inputs[0]["targetSlot"] == "0"


def numeric_workflow():
    raw = workflow()
    raw["nodes"].extend(
        [
            {
                "id": 4,
                "type": "PrimitiveInt",
                "widgets_values_named": {"value": 97},
                "outputs": [{"type": "INT"}],
            },
            {"id": 5, "type": "ShotMillIOBridgeIn", "inputs": [{"name": "*", "link": 3}]},
        ]
    )
    raw["nodes"][2]["inputs"].append({"name": "frames", "type": "INT", "link": 4})
    raw["links"].extend([[3, 4, 0, 5, 0, "INT"], [4, 5, 0, 3, 1, "INT"]])
    return raw


def test_bridge_numeric_inputs_have_stable_identity_and_do_not_consume_media_slots(bridge_graph):
    raw = numeric_workflow()
    ports, _ = bridge_graph["_bridge_ports"](raw)
    assert [(port["type"], port["targetPort"]) for port in ports] == [
        ("IMAGE", "image_0"),
        ("INT", "frames"),
    ]
    prompt = bridge_graph["_canvas_prompt"](raw)
    bridge_graph["_bind_input_markers"](
        prompt,
        {
            "assets": [],
            "inputSlots": [None],
            "numericInputs": {"3:frames:4": 145},
        },
        raw,
    )
    assert prompt["4"]["inputs"]["value"] == 145
    assert prompt["3"]["inputs"]["frames"] == ["4", 0]
    assert "image_0" not in prompt["3"]["inputs"]
    assert raw["nodes"][3]["widgets_values_named"]["value"] == 97


def test_bridge_preserves_default_numeric_values_without_binding(bridge_graph):
    raw = numeric_workflow()
    prompt = bridge_graph["_canvas_prompt"](raw)
    bridge_graph["_bind_input_markers"](prompt, {"assets": [], "inputSlots": [None]}, raw)
    assert prompt["4"]["inputs"]["value"] == 97
    assert prompt["3"]["inputs"]["frames"] == ["4", 0]


@pytest.mark.parametrize(
    ("node_type", "value_type", "value"),
    [
        ("PrimitiveInt", "INT", 145),
        ("PrimitiveFloat", "FLOAT", 6.5),
    ],
)
def test_api_numeric_port_type_and_fanout_match_execution(
    bridge_graph,
    node_type,
    value_type,
    value,
):
    raw = {
        "prompt": {
            "1": {"class_type": node_type, "inputs": {"value": 1}},
            "2": {"class_type": "ShotMillIOBridgeIn", "inputs": {"*": ["1", 0]}},
            "3": {
                "class_type": "Generator",
                "inputs": {
                    "frames": ["2", 0],
                    "image_count": ["2", 0],
                },
            },
        }
    }
    ports, _ = bridge_graph["_bridge_ports"](raw)
    assert [(port["type"], port["targetPort"], port["sourceNodeId"]) for port in ports] == [
        (value_type, "frames", "1"),
    ]
    prompt = json.loads(json.dumps(raw["prompt"]))
    bridge_graph["_bind_input_markers"](
        prompt,
        {
            "assets": [],
            "inputSlots": [],
            "numericInputs": {"3:frames:1": value},
        },
        raw,
    )
    assert prompt["1"]["inputs"]["value"] == value
    assert prompt["3"]["inputs"] == {"frames": ["1", 0], "image_count": ["1", 0]}
    assert raw["prompt"]["1"]["inputs"]["value"] == 1


@pytest.mark.parametrize("numeric", [{"3:frames:4": 1.5}, {"missing": 4}, {"3:frames:4": True}])
def test_bridge_rejects_bad_numeric_values_and_stale_ids(bridge_graph, numeric):
    raw = numeric_workflow()
    prompt = bridge_graph["_canvas_prompt"](raw)
    with pytest.raises(ValueError):
        bridge_graph["_bind_input_markers"](
            prompt,
            {
                "assets": [],
                "inputSlots": [None],
                "numericInputs": numeric,
            },
            raw,
        )


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


def test_parameter_selectors_only_override_task_values(bridge_graph):
    prompt = {
        "r": {
            "class_type": "ShotMillResolutionSelector",
            "inputs": {"resolution": "720p", "aspect_ratio": "9:16", "alignment": 32},
        },
        "d": {
            "class_type": "ShotMillDurationSelector",
            "inputs": {"seconds": 6, "model": "H3", "fps": 24},
        },
    }
    bridge_graph["_bind_parameter_selectors"](
        prompt, {"resolution": "1080p", "durationSeconds": 10, "model": "custom", "fps": 100}
    )
    assert prompt["r"]["inputs"] == {"resolution": "1080p", "aspect_ratio": "9:16", "alignment": 32}
    assert prompt["d"]["inputs"] == {"seconds": 10, "model": "H3", "fps": 24}
    for params in ({"resolution": "bad"}, {"durationSeconds": -1}, {"durationSeconds": True}):
        with pytest.raises(ValueError):
            bridge_graph["_bind_parameter_selectors"](prompt, params)
