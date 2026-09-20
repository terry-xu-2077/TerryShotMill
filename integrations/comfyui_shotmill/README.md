# ShotMill Bridge node runtime

This directory owns the marker node runtime (`nodes.py`) and Bridge API
(`bridge_api.py`) installed in `ComfyUI/custom_nodes/ComfyUI-ShotMill/`.
The complete package includes `__init__.py`, the Python modules, and `web/`.
Copy this directory to `ComfyUI/custom_nodes/ComfyUI-ShotMill/`. Back up installed
files before deployment. Python changes require restarting ComfyUI when its
queue is idle; browser extension updates require refreshing the ComfyUI page.
The package uses ComfyUI's own runtime dependencies. Workflows may require
additional custom nodes and models; these are not bundled with ShotMill.

Run `python -m pytest tests/contract/test_bridge_node_provider.py` to check
sparse ports, output arity and identity-preserving pass-through. Set
`SHOTMILL_BRIDGE_NODES` to the installed file to test the deployed copy.

Absent input slots return `None` at the same output index. They never shift
later inputs forward. A downstream node must support an absent value if its
upstream source is disabled; required inputs still need valid data.

Graph metadata contracts are in `tests/contract/test_bridge_workflow_provider.py`.
They exercise the production graph functions without importing the GPU server.
Empty extension sockets are not assets. Terminal port tracing follows Bridge
slots and wired/wireless bus lane IDs instead of using the intermediate port
label. Application API response models must preserve this metadata.

`canvas_compiler.py` compiles an execution copy inside Bridge. Deploy it together
with `bridge_api.py`. It expands serialized subgraphs, resolves bypassed nodes,
Set/Get routing and TerryXu wired/wireless bus lane identities, and omits notes.
Connected widgets still consume their serialized positions. Submission prunes
unreachable non-output nodes before ComfyUI's own validation. Unknown runtime
nodes remain validation errors, not silently replaced generation algorithms.
Contracts are in `tests/contract/test_canvas_compiler.py`; this is not a claim
that every third-party frontend-only extension is supported.

Hardware smoke on 2026-09-20: the saved canvas `异星边境_稳定720P.json`
ran through Bridge, job `job-8e05c11795654222a049b5ba9beaa1ea`, Comfy prompt
`53fd3936-93a7-4208-9997-b7d808faf9e3`. Native SaveVideo wrote
`output/shotmill/results/<job-id>/异星边境_CUT_01_00001_.mp4`.
Verified H.264 + AAC, 864x480, 24 fps, 8 seconds, and byte-identical result
download. The filename says 720P but the saved workflow currently selects
0.4 megapixels and 8 seconds; no generation parameters were lowered by Bridge.

Job status reads the live queue before history, distinguishing queued, running,
completed, failed, and not_found. Known failed jobs return HTTP 200 with their
execution error; only missing jobs return 404. Completed/failed responses are
persisted as `terminalState` in `output/shotmill/jobs.json` using atomic file
replacement. Result downloads can therefore outlive ComfyUI's in-memory history.
Do not discard this index while retaining output files.

When upgrading an older installation, wait for all queues to become idle, back
up the index and installed package, and capture available terminal responses
from the old Bridge API into matching job entries before restarting ComfyUI.
Preserve all other index fields and reject changed prompt IDs or concurrent
index changes. Never infer a completed job merely from its output directory.

Final hardware acceptance on 2026-09-20: all eight character tasks completed
with the saved workflow above. After an idle restart of ComfyUI and ShotMill,
all eight Bridge downloads matched the application copies by SHA256, all files
decoded successfully, and every application video player reached its end.
Playback evidence and file hashes are recorded in
`.artifacts/live-results-final/{playback,file-checks}.json` in the project root.
This verifies the production path, not subjective speech or lip-sync quality.
