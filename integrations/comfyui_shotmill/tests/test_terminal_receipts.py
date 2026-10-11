"""Completion persistence must not depend on a connected client."""
import ast
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load():
    path = Path(__file__).resolve().parents[1] / "terminal_receipts.py"
    spec = importlib.util.spec_from_file_location("terminal_receipts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Queue:
    def __init__(self, owned=True):
        self.mutex = threading.RLock()
        extra = {"terryflow_job_id": "job-1"} if owned else {}
        self.currently_running = {7: (0, "prompt-1", {}, extra)}
        self.history = {}

    def task_done(self, item_id, history_result, status, process_item=None):
        with self.mutex:
            item = self.currently_running.pop(item_id)
            self.history[item[1]] = {**history_result, "status": status}
        return "original-return"

    def get_history(self, prompt_id):
        return {prompt_id: self.history[prompt_id]} if prompt_id in self.history else {}

    def get_current_queue(self):
        return [], []


class TerminalReceiptTests(unittest.TestCase):
    def test_production_status_recovers_from_receipt_without_prior_client_query(self):
        module = load()
        source = Path(__file__).resolve().parents[1] / "bridge_api.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if
                     isinstance(node, ast.ImportFrom) and node.module == "__future__"
                     or isinstance(node, ast.FunctionDef) and node.name in {
                         "_job_state", "_history_results", "_load_index", "_save_index"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = Queue()
            module.install_completion_recorder(queue, root / "receipts")
            index = root / "jobs.json"
            index.write_text(json.dumps({"jobs": {"job-1": {"promptId": "prompt-1"}}}), encoding="utf-8")
            queue.task_done(7, {"outputs": {"save": {"videos": [{
                "filename": "clip.mp4", "type": "output", "subfolder": "original",
            }]}}}, {"status_str": "success"})
            queue.history.clear()
            scope = {
                "json": json, "Path": Path, "JOB_INDEX": index,
                "RECEIPT_ROOT": root / "receipts", "read_receipt": module.read_receipt,
                "PromptServer": SimpleNamespace(instance=SimpleNamespace(prompt_queue=queue)),
            }
            exec(compile(tree, str(source), "exec"), scope)
            state = scope["_job_state"]("job-1")
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["results"][0]["relativePath"], "original/clip.mp4")
            self.assertEqual(json.loads(index.read_text(encoding="utf-8"))["jobs"]["job-1"]["terminalState"], state)

    def test_server_restart_marks_only_unfinished_admitted_jobs_failed(self):
        module = load()
        source = Path(__file__).resolve().parents[1] / "bridge_api.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if
                     isinstance(node, ast.ImportFrom) and node.module == "__future__"
                     or isinstance(node, ast.FunctionDef) and node.name in {
                         "_job_state", "_history_results", "_load_index", "_save_index"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "jobs.json"
            index.write_text(json.dumps({"jobs": {
                "interrupted": {"promptId": "p1", "submissionState": "queued",
                                "serverSessionId": "old"},
                "uncertain": {"promptId": "p2", "submissionState": "prepared",
                              "serverSessionId": "old"},
                "same-session": {"promptId": "p3", "submissionState": "queued",
                                 "serverSessionId": "new"},
                "completed": {"promptId": "p4", "submissionState": "queued",
                              "serverSessionId": "old"},
            }}), encoding="utf-8")
            receipts = root / "receipts"
            module.write_receipt(receipts, "completed", "p4", {
                "outputs": {"save": {"videos": [{"filename": "clip.mp4", "type": "output"}]}},
                "status": {"status_str": "success"},
            })
            queue = Queue()
            queue.currently_running.clear()
            scope = {
                "json": json, "Path": Path, "JOB_INDEX": index,
                "RECEIPT_ROOT": receipts, "read_receipt": module.read_receipt,
                "SERVER_SESSION_ID": "new",
                "PromptServer": SimpleNamespace(instance=SimpleNamespace(prompt_queue=queue)),
            }
            exec(compile(tree, str(source), "exec"), scope)
            interrupted = scope["_job_state"]("interrupted")
            self.assertEqual(interrupted["status"], "failed")
            self.assertEqual(interrupted["error"]["code"], "server_exited")
            self.assertEqual(scope["_job_state"]("uncertain")["status"], "not_found")
            self.assertEqual(scope["_job_state"]("same-session")["status"], "not_found")
            self.assertEqual(scope["_job_state"]("completed")["status"], "completed")

    def test_completion_survives_history_loss_without_polling(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status in ("success", "error"):
                with self.subTest(status=status):
                    queue = Queue()
                    module.install_completion_recorder(queue, root)
                    entry = {"outputs": {"save": {"images": [{"filename": "clip.mp4"}]}}}
                    self.assertEqual(queue.task_done(7, entry, {"status_str": status}), "original-return")
                    queue.history.clear()
                    receipt = module.read_receipt(root, "job-1", "prompt-1")
                    self.assertEqual(receipt["outputs"], entry["outputs"])
                    self.assertEqual(receipt["status"]["status_str"], status)
                    self.assertIsNone(module.read_receipt(root, "job-1", "other-prompt"))

    def test_unowned_tasks_are_not_recorded_and_install_is_idempotent(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = Queue(owned=False)
            module.install_completion_recorder(queue, root)
            wrapped = queue.task_done
            module.install_completion_recorder(queue, root)
            self.assertIs(queue.task_done, wrapped)
            queue.task_done(7, {"outputs": {}}, {"status_str": "success"})
            self.assertEqual(list(root.iterdir()), [])

    def test_storage_failure_does_not_break_comfy_worker_or_claim_a_receipt(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = Queue()
            module.install_completion_recorder(queue, root)
            with patch.object(module, "write_receipt", side_effect=OSError("disk full")):
                with self.assertLogs(level="ERROR"):
                    self.assertEqual(queue.task_done(7, {"outputs": {}}, {"status_str": "success"}), "original-return")
            self.assertIsNone(module.read_receipt(root, "job-1", "prompt-1"))
            self.assertIn("prompt-1", queue.history)

    def test_atomic_publish_failure_keeps_previous_receipt_and_removes_temporary_file(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = {"outputs": {"old": []}, "status": {"status_str": "success"}}
            module.write_receipt(root, "job-1", "prompt-1", original)
            with patch.object(module.os, "replace", side_effect=OSError("publication failed")):
                with self.assertRaises(OSError):
                    module.write_receipt(root, "job-1", "prompt-1", {"outputs": {}})
            self.assertEqual(module.read_receipt(root, "job-1", "prompt-1"), original)
            self.assertEqual([path.name for path in root.iterdir()], ["job-1.json"])

    def test_receipt_does_not_copy_prompt_or_extra_data(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = Queue()
            module.install_completion_recorder(queue, root)
            queue.task_done(7, {"outputs": {}, "prompt": "private graph", "extra_data": {
                "token": "private credential",
            }}, {"status_str": "success"})
            receipt = module.read_receipt(root, "job-1", "prompt-1")
            self.assertEqual(set(receipt), {"outputs", "status"})
            self.assertNotIn("private", (root / "job-1.json").read_text(encoding="utf-8"))

    def test_identifiers_cannot_escape_receipt_directory(self):
        module = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for identifier in ("../escape", "a/b", "a\\b", "", ".", ".."):
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    module.write_receipt(root, identifier, "p", {"outputs": {}})


if __name__ == "__main__":
    unittest.main()
