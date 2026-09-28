"""Opt-in real Bridge acceptance using two disposable ShotMill HTTP processes.

The named workflow must already be installed. This submits real jobs and retains
their Bridge history/output; it never changes existing workflows or real projects.
"""

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

from bridge_disconnect_proxy import disconnect_proxy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "integration"))
from test_two_instance_isolation import independent_server  # noqa: E402


def generate(client, disconnect=None, *, resume=None, pause=False, offline_seconds=0):
    if resume is None:
        response = client.post("/api/v1/projects", json={"title": "Isolated Bridge acceptance"})
        assert response.status_code == 201, response.text
        project = response.json()["id"]
        route = f"/api/v1/projects/{project}"
        response = client.post(f"{route}/tasks", json={
            "title": "Video transport", "userPrompt": "Transport acceptance",
            "promptSource": "user", "durationSeconds": 1, "generation": {}, "assetBindings": [],
        })
        assert response.status_code == 201, response.text
        task = response.json()["id"]
        response = client.post(f"{route}/tasks/{task}/generation", json={})
        assert response.status_code == 202, response.text
        job = response.json()["id"]
    else:
        project, task, job = (resume[key] for key in ("projectId", "taskId", "jobId"))
        route = f"/api/v1/projects/{project}"
    deadline = time.monotonic() + 60 + offline_seconds
    offline_started = None
    observed_offline = 0.0
    while True:
        response = client.get(f"/api/v1/jobs/{job}")
        assert response.status_code == 200, response.text
        state = response.json()["status"]
        if disconnect is not None and disconnect.interrupted.is_set():
            if not disconnect.reconnect.is_set():
                assert state == "running", response.text
                workspace = client.get(f"{route}/workspace")
                assert workspace.status_code == 200, workspace.text
                summary = next(item for item in workspace.json()["tasks"] if item["id"] == task)
                progress = summary["timing"].get("generationProgress") or {}
                if progress.get("connectionState") == "reconnecting":
                    assert disconnect.blocked_reads > 0
                    if pause:
                        return {"projectId": project, "taskId": task, "jobId": job}
                    if offline_started is None:
                        offline_started = time.monotonic()
                    observed_offline = time.monotonic() - offline_started
                    if observed_offline >= offline_seconds:
                        disconnect.reconnect.set()
        if state == "completed":
            break
        assert state not in {"failed", "cancelled"}, response.text
        assert time.monotonic() < deadline, response.text
        time.sleep(0.2)
    response = client.get(f"{route}/tasks/{task}/results")
    assert response.status_code == 200, response.text
    results = response.json()["items"]
    assert len(results) == 1, results
    response = client.get(results[0]["videoUrl"])
    assert response.status_code == 200, response.text
    assert b"ftyp" in response.content[:32], "Expected actual MP4 output"
    if disconnect is not None:
        assert disconnect.reconnect.is_set(), "No reconnection was observed"
        assert disconnect.submissions == [job], "Remote work was submitted more than once"
    return {"projectId": project, "jobId": job, "resultId": results[0]["id"],
            "observedOfflineSeconds": round(observed_offline, 2),
            "sha256": hashlib.sha256(response.content).hexdigest(), "bytes": len(response.content)}


def verify_peers(left, right, first, process_ids):
    evidence = [first, generate(right)]
    assert evidence[0]["jobId"] != evidence[1]["jobId"]
    for client, other in ((left, evidence[1]), (right, evidence[0])):
        assert client.get(f"/api/v1/jobs/{other['jobId']}").status_code == 404
    print(json.dumps({"instances": evidence, "processIds": process_ids}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--disconnect", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--offline-seconds", type=float, default=0)
    args = parser.parse_args()
    if args.restart and not args.disconnect:
        parser.error("--restart requires --disconnect")
    if not 0 <= args.offline_seconds <= 3600:
        parser.error("--offline-seconds must be between 0 and 3600")
    if args.offline_seconds and not args.disconnect:
        parser.error("--offline-seconds requires --disconnect")
    environment = {
        "SHOTMILL_COMFYUI_BASE_URL": args.base_url,
        "SHOTMILL_COMFYUI_WORKFLOW_TEMPLATE": args.workflow_id,
    }
    with tempfile.TemporaryDirectory(prefix="shotmill-two-bridge-") as directory, (
        disconnect_proxy(args.base_url)
    ) as (proxy_url, disconnect):
        root = Path(directory)
        left_environment = {**environment, "SHOTMILL_COMFYUI_BASE_URL": proxy_url} if (
            args.disconnect
        ) else environment
        with independent_server(root / "right", provider_environment=environment) as (right, rp):
            with independent_server(
                root / "left", provider_environment=left_environment,
            ) as (left, lp):
                assert lp != rp and left.base_url != right.base_url
                first = generate(
                    left, disconnect if args.disconnect else None, pause=args.restart,
                    offline_seconds=args.offline_seconds,
                )
                if not args.restart:
                    verify_peers(left, right, first, [lp, rp])
            if args.restart:
                # The owned test process has exited; reuse only its persistent data.
                with independent_server(
                    root / "left", provider_environment=left_environment,
                ) as (reopened, new_pid):
                    assert new_pid not in {lp, rp}
                    recovered = generate(
                        reopened, disconnect, resume=first, offline_seconds=args.offline_seconds,
                    )
                    assert recovered["jobId"] == first["jobId"]
                    verify_peers(reopened, right, recovered, [lp, new_pid, rp])


if __name__ == "__main__":
    main()
