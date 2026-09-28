# ComfyUI-TerryFlowBridge

Reusable workflow input/output bridge for ComfyUI. Install this repository as
`ComfyUI/custom_nodes/ComfyUI-TerryFlowBridge` and restart ComfyUI while idle.
It uses ComfyUI's existing Python dependencies. New workflows can use
**Terry Flow Bridge In / Out**; existing ShotMill node class names remain supported.
Do not load this package alongside the old `ComfyUI-ShotMill` package: both own
the same compatibility routes and node names. Back up and disable the old package
before an idle upgrade. Preserve `input/shotmill` and `output/shotmill` data;
the storage layout intentionally remains unchanged during migration.

## Cancelling an uncertain submission

`POST /terryflow/v1/jobs/{job_id}/cancel-submission` (also available under
`/shotmill/v1`) serializes with submission admission. For an unused logical ID,
it persists a cancellation record before replying `status: cancelled`. Future
submissions using that ID receive HTTP 409 `submission_cancelled`; repeat
cancellation and status queries return the saved cancellation.

For an existing queued/running job, this endpoint returns its current status and
remote prompt ID; it does **not** stop execution. The caller must use targeted
ComfyUI queue deletion/interruption and observe the terminal state. Completed
results remain completed. A saved receipt with missing queue/history returns
409 `submission_state_unknown`, not a cancellation claim. A write failure cannot
return success. Preserve the job index across upgrades and restarts: deleting it
also destroys deduplication and cancellation protection.

## Versioned application contracts (0.5.0)

`GET /terryflow/v1/health` advertises protocol versions, supported application
contracts and capabilities. New job and preflight requests must specify:

```json
{"applicationContract": {"name": "generic", "version": 1}}
```

- `generic@1`: common workflow compilation, port binding and output collection.
  Does not interpret ShotMill video selectors or remap H3 prompt references.
- `shotmill.video@1`: additionally binds video selectors and adapts H3 references.
  ShotMill's video adapter explicitly declares this contract.
- Unknown names/versions are rejected before validation or enqueueing.
- `/shotmill/v1` remains an alias and defaults omitted declarations to
  `shotmill.video@1`, preserving existing applications and workflow files.

Application handlers are registered in `application_contracts.py`; names and
versions identify behavior, not authentication or permissions. This release is
for a single user's trusted LAN, without pairing/authentication. Do not expose
ComfyUI or these routes to the public internet.

### ShotMill submission compatibility

New ShotMill jobs require protocol 1, `shotmill.video@1`, and explicit boolean
capabilities `workflowSnapshot`, `preflight`, `idempotentSubmit`, `assetUpload`,
`resultDownload`, `resultSha256`, `cancelSubmission`, and `durableCompletion`. Package version alone
does not imply support. Upgrade the Bridge before submitting new jobs with the
updated ShotMill client; incompatible health responses fail before media upload
or generation submission.

ShotMill freezes the agreement alongside the server address and workflow in the
Job profile. Recovery uses that agreement without renegotiating or resubmitting.
Negotiated jobs require `X-Content-SHA256` on downloaded results; missing or
incorrect digests prevent local result publication. Historical jobs without an
agreement retain `/shotmill/v1` recovery; absent digests remain explicitly marked
unverified. A new profile missing its agreement is not treated as a legacy job.

### Completion retention (0.5.1)

`durableCompletion: true` means new Bridge submissions carry an ownership marker.
The ComfyUI worker completion hook atomically writes an fsynced per-job receipt
under `output/shotmill/receipts` before returning from completion. It records only
outputs and status, not the prompt graph or client credentials. Status queries
can recover from this receipt after ComfyUI history is cleared, without a prior
client poll. It does not record unrelated ComfyUI jobs. Keep these receipts and
`output/shotmill/jobs.json` across upgrades; neither is automatically expired.

Successful uploads and results are retained without an automatic expiry or a
delete-on-download acknowledgement. ShotMill local deletion does not delete
server files. Administrators must not manually remove uncollected inputs,
results or receipts. Disk-full errors are logged and cannot guarantee durability;
in-memory history remains available for a later status query. This hook is not
a transaction with ComfyUI's execution engine: a process crash during completion
before receipt publication remains an uncertain outcome, never permission to
automatically resubmit. Jobs admitted before this upgrade lack the ownership
marker and retain their previous client-query-based persistence behavior.

CPU-only package smoke tests (no ShotMill or GPU dependencies):

```text
python -m unittest discover -s tests
```

Uploads are streamed into temporary files and published under
`input/shotmill/assets/sha256/<digest>/<filename>`. Uploading new content for an
existing asset ID never changes a previously submitted file path. Send a
`sha256` multipart field to validate transfer integrity; responses include the
computed digest and byte count. Interrupted transfers remove their temporary
file. An existing damaged blob is rejected, not overwritten. Unreferenced upload
cleanup is not automatic in this migration release.

Full graph/provider integration and native GPU acceptance remain in the ShotMill
consumer test suite. The notes below document historical deployments and do not
claim live acceptance of the new package.

## Pending Flow Bridge migration: submission safety

The migration work now reserves a logical `jobId` in the job index before
enqueueing. Concurrent retries with an identical payload return the original
prompt identity; changes to an existing job payload return `409 job_id_conflict`.
Only `clientId` is excluded from the request fingerprint. Old receipts without a
fingerprint remain queryable but cannot be resubmitted under that identity.

A prepared receipt without observable queue/history evidence returns
`409 submission_state_unknown`; the server never assumes that retrying inference
is safe. A lost response after enqueue can be recovered using the recorded prompt
identity. A corrupt index blocks submission rather than being replaced. This is
tested against the production route functions with a deterministic queue, not yet
deployed or accepted on the live ComfyUI server.

This directory owns the marker node runtime (`nodes.py`) and Bridge API
(`bridge_api.py`) installed in `ComfyUI/custom_nodes/ComfyUI-ShotMill/`.
The complete package includes `__init__.py`, the Python modules, and `web/`.
Copy this directory to `ComfyUI/custom_nodes/ComfyUI-ShotMill/`. Back up installed
files before deployment. Python changes require restarting ComfyUI when its
queue is idle; browser extension updates require refreshing the ComfyUI page.
The package uses ComfyUI's own runtime dependencies. Workflows may require
additional custom nodes and models; these are not bundled with ShotMill.

Bridge 0.3.0 adds read-only `GET /shotmill/v1/workflows/snapshot?workflowId=...`.
It reads a workflow once, compiles its canvas and returns the raw graph, compiled
prompt, input ports and a canonical SHA-256 digest. ShotMill stores this content
in the immutable Job configuration. Submitting `workflowSnapshot` executes that
copy even if the original file was edited or deleted; invalid digests are rejected.
Prompt AI's direct `prompt` submission remains unchanged. Older queued video
Jobs without a content snapshot must be resubmitted explicitly.

Snapshot capture does not upload assets or enqueue work. Node code and model
files themselves are not frozen by a workflow snapshot.

Bridge 0.3.1 adds read-only `POST /shotmill/v1/workflows/validate`. It accepts the
same frozen workflow, prompt, media slot metadata and resolved numeric inputs
as execution, and shares its graph binding, optional-input removal and output
rewriting. ComfyUI validates installed nodes, required inputs, connection types,
model choices, literal value limits and dependency/loop structure. Dynamic V3
choice keys receive an additional shared check because native schema expansion
can omit an invalid choice entirely. A failing active output rejects a video
workflow instead of silently running only its other outputs.

Only assigned native LoadImage/LoadVideo/LoadAudio file checks are deferred until
upload. The deferred set is derived by Bridge binding, not accepted from clients;
workflow-owned files remain validated. The native validation cache skips only
single-file loaders, while consumers still check their output types. No global
validator or node registration is patched. Both validation and full generation
revalidate runtime inputs; no model inference or media decoding happens during
preflight, so those runtime failures remain possible. Prompt AI direct-prompt
submission retains its existing behavior.

Local acceptance covers fourteen native/runtime cases, including both real H3
canvases, with unchanged input files, queue and job index. An additional native
25-frame video passed preflight and generation after its workflow file had been
deleted. Evidence: `.artifacts/preflight-live/`.

Bridge 0.2.1 recognizes H3 video references connected through native
`LoadVideo -> Bridge In -> GetVideoComponents -> ref_videos` chains. An empty
video slot disconnects the optional H3 reference instead of leaving an invalid
decoder dependency. Existing direct image and video reference numbering is preserved.
ShotMill prepares local context media before queuing and supplies it to a free
compatible port. A workflow without a free VIDEO input cannot accept segment context.

Bridge 0.2.2 excludes input/temporary previews from downloadable results,
including old cached terminal states. Native LoadVideo emits an input preview;
that preview must not become the generated output or shift download indices.

Bridge 0.2.0 exposes PrimitiveInt/PrimitiveFloat inputs separately from media
slots. Jobs can supply `numericInputs` keyed by the catalogue's
`targetNodeId:targetPort:sourceNodeId`; absent bindings preserve saved defaults.
Finite values and integer inputs are validated before queue submission. Numeric
bindings update the execution copy only. ShotMill presets own the seconds/frame
conversion rules; Bridge receives the resolved values. PrimitiveBoolean remains
a workflow default rather than accepting numeric overrides.

Local numeric acceptance on 2026-09-21 used the real Provider and native
CreateVideo/SaveVideo nodes: 2/3 seconds at 24 fps with a 4n+1 rule produced
49/73 frames and fully decoded MP4 files. All 17 prior Bridge job states survived
the idle upgrade unchanged. Evidence is in
`.artifacts/bridge-numeric-20260921/numeric-evidence.json`. This is numeric and
encoding acceptance, not a model-generation quality test.

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


## Bridge 0.4.0 parameter selectors

Add `ShotMill Bridge 分辨率选择器` and connect its INT `width` / `height`
outputs to the video node. ShotMill sends 480p / 720p / 1080p; aspect ratio
and pixel alignment remain workflow settings (default 16:9 and 32 pixels).
Dimensions round up to that alignment: 720p becomes 1280×736 at 32-pixel alignment.

Add `ShotMill Bridge 秒数选择器` and connect `length` directly to H3's
length input, optionally connecting `fps` to video encoding. Default H3 mode
uses 24 fps and rounds upward to 17n+5 frames (5s=124, 6s=158, 10s=243).
The workflow's custom mode uses its fps, frame_multiple and frame_offset;
ShotMill sends only seconds and never overrides these calculation settings.
The same binding runs during preflight and execution on the frozen graph copy.
No Bridge In numeric binding is required. Workflows without the new nodes
keep their existing saved defaults and legacy explicit numeric bindings.
