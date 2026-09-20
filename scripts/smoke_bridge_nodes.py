"""Exercise installed Bridge sockets through its API, without loading models."""
from __future__ import annotations

import io
import os
import time
from uuid import uuid4

import httpx
from PIL import Image


def main():
    job_id = f"bridge-port-smoke-{uuid4().hex[:12]}"
    prompt = {
        "1": {"class_type": "EmptyImage", "inputs": {
            "width": 16, "height": 16, "batch_size": 1, "color": 16711680,
        }},
        "2": {"class_type": "EmptyImage", "inputs": {
            "width": 16, "height": 16, "batch_size": 1, "color": 65280,
        }},
        "284": {"class_type": "ShotMillIOBridgeIn", "inputs": {
            "*": ["1", 0], "* 2": ["2", 0],
        }},
        "285": {"class_type": "ShotMillIOBridgeIn", "inputs": {
            "* 3": "third reference", "* 10": "tenth reference",
        }},
    }
    for index in range(2):
        output_id = str(300 + index)
        prompt[output_id] = {"class_type": "ShotMillIOBridgeOut", "inputs": {
            "*": ["284", index],
        }}
        prompt[str(310 + index)] = {"class_type": "SaveImage", "inputs": {
            "images": [output_id, 0],
            "filename_prefix": f"shotmill/results/{job_id}/port-{index + 1}",
        }}
    previews = {"320": ("284", 8), "321": ("285", 0), "322": ("285", 2),
                "323": ("285", 9), "324": ("285", 255)}
    for node_id, source in previews.items():
        prompt[node_id] = {"class_type": "PreviewAny", "inputs": {"source": list(source)}}

    with httpx.Client(base_url=os.getenv("COMFYUI_URL", "http://127.0.0.1:8188"),
                      timeout=20, trust_env=False) as client:
        response = client.post("/shotmill/v1/jobs", json={"jobId": job_id, "prompt": prompt})
        response.raise_for_status()
        print(f"Submitted {job_id}: {response.json()['promptId']}", flush=True)
        deadline = time.monotonic() + 90
        while True:
            state = client.get(f"/shotmill/v1/jobs/{job_id}").json()
            if state["status"] in {"completed", "failed"}:
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"Still running; inspect {job_id}, do not resubmit")
            time.sleep(0.5)
        assert state["status"] == "completed", state
        outputs = state["nodeOutputs"]
        for node_id, expected in {"320": "None", "321": "None", "322": "third reference",
                                  "323": "tenth reference", "324": "None"}.items():
            assert outputs[node_id]["text"] == [expected], outputs[node_id]
        assert len(state["results"]) == 2, state
        for index, metadata in enumerate(state["results"]):
            image_bytes = client.get(f"/shotmill/v1/results/{job_id}/files/{index}")
            image_bytes.raise_for_status()
            with Image.open(io.BytesIO(image_bytes.content)) as image:
                expected = (255, 0, 0) if "port-1" in metadata["filename"] else (0, 255, 0)
                assert image.size == (16, 16)
                assert image.convert("RGB").getpixel((0, 0)) == expected
        print("PASS: images, Bridge Out, sparse text, missing ports 1/9/256 and native saving")


if __name__ == "__main__":
    main()
