"""Worker-side completion receipts, independent of client polling and job-index writes."""
from __future__ import annotations

import functools
import json
import logging
import os
import re
import tempfile
from pathlib import Path

LOG = logging.getLogger(__name__)


def _path(root: Path, job_id: str) -> Path:
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]*", job_id):
        raise ValueError("Invalid receipt job identifier")
    root = root.resolve()
    candidate = (root / (job_id + ".json")).resolve()
    if candidate.parent != root:
        raise ValueError("Receipt path escapes its directory")
    return candidate


def write_receipt(root: Path, job_id: str, prompt_id: str, entry: dict) -> None:
    target = _path(root, job_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "jobId": job_id, "promptId": prompt_id, "entry": entry}
    pending = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=".pending-", delete=False,
        ) as stream:
            pending = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, target)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def read_receipt(root: Path, job_id: str, prompt_id: str) -> dict | None:
    try:
        data = json.loads(_path(root, job_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        LOG.exception("Unable to read Terry Flow Bridge receipt for %s", job_id)
        return None
    if (
        not isinstance(data, dict) or data.get("version") != 1
        or data.get("jobId") != job_id or data.get("promptId") != prompt_id
        or not isinstance(data.get("entry"), dict)
    ):
        return None
    return data["entry"]


def install_completion_recorder(queue, root: Path) -> None:
    if getattr(queue, "_terryflow_completion_recorder", False):
        return
    original = queue.task_done

    @functools.wraps(original)
    def task_done(item_id, *args, **kwargs):
        # ComfyUI removes the running tuple inside task_done. Capture only the
        # Bridge's own identity before that; never mutate its graph or return value.
        with queue.mutex:
            item = queue.currently_running.get(item_id)
            extra = item[3] if item and len(item) > 3 else None
            job_id = extra.get("terryflow_job_id") if isinstance(extra, dict) else None
            prompt_id = str(item[1]) if item else ""
            result = original(item_id, *args, **kwargs)
            # Hold ComfyUI's reentrant queue lock until the history snapshot has
            # been captured, so a concurrent clear-history cannot win this gap.
            entry = None
            if job_id:
                try:
                    entry = queue.get_history(prompt_id=prompt_id).get(prompt_id)
                except Exception:
                    LOG.exception("Failed to capture Terry Flow Bridge completion for %s", job_id)
        if job_id:
            try:
                if isinstance(entry, dict):
                    # Do not duplicate prompt graphs or any credentials in extra_data.
                    receipt = {key: entry[key] for key in ("outputs", "status") if key in entry}
                    write_receipt(root, job_id, prompt_id, receipt)
            except Exception:
                # Disk errors must be visible, but must not kill ComfyUI's worker.
                # History remains available for later client-driven persistence.
                LOG.exception("Failed to persist Terry Flow Bridge completion for %s", job_id)
        return result

    queue.task_done = task_done
    queue._terryflow_completion_recorder = True
