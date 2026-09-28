"""Exercise the installed ComfyUI queue implementation without GPU/server imports."""
from __future__ import annotations

import argparse
import ast
import copy
import heapq
import importlib.util
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, NamedTuple, Optional


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfyui-root", type=Path, required=True)
    args = parser.parse_args()
    source = args.comfyui_root / "execution.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    queue_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PromptQueue"
    )
    module = ast.parse("from __future__ import annotations")
    module.body.append(queue_class)
    scope = {
        "threading": threading, "copy": copy, "heapq": heapq,
        "NamedTuple": NamedTuple, "Literal": Literal, "Optional": Optional, "List": list,
        "MAXIMUM_HISTORY_SIZE": 10000,
    }
    exec(compile(module, str(source), "exec"), scope)
    receipt_path = (
        Path(__file__).resolve().parents[1]
        / "integrations/comfyui_shotmill/terminal_receipts.py"
    )
    spec = importlib.util.spec_from_file_location("bridge_receipts", receipt_path)
    assert spec is not None and spec.loader is not None
    receipts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receipts)
    queue = scope["PromptQueue"](SimpleNamespace(queue_updated=lambda: None))
    with tempfile.TemporaryDirectory(prefix="shotmill-completion-") as directory:
        root = Path(directory)
        receipts.install_completion_recorder(queue, root)
        queue.put((0, "prompt-1", {}, {"terryflow_job_id": "job-1"}, [], {}))
        _item, item_id = queue.get(timeout=0)
        queue.task_done(
            item_id,
            {"outputs": {"save": {"images": [{"filename": "result.png", "type": "output"}]}}},
            queue.ExecutionStatus("success", True, []),
        )
        queue.history.clear()
        receipt = receipts.read_receipt(root, "job-1", "prompt-1")
        assert receipt["status"]["completed"] is True
        assert receipt["outputs"]["save"]["images"][0]["filename"] == "result.png"
    print("PASS installed ComfyUI PromptQueue completion persistence (CPU-only, no live server)")


if __name__ == "__main__":
    main()
