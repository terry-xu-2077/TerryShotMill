import hashlib
import json
from pathlib import Path


def test_bridge_snapshot_matches_pinned_file_set_and_digests():
    integrations = Path(__file__).resolve().parents[2] / "integrations"
    lock = json.loads((integrations / "terryflow-bridge.lock.json").read_text(encoding="utf-8"))
    assert lock["repository"] == "https://github.com/terry-xu-2077/ComfyUI-TerryFlowBridge.git"
    assert len(lock["revision"]) == 40
    assert all(char in "0123456789abcdef" for char in lock["revision"])
    assert lock["hashNormalization"] == "utf8-lf"
    assert lock["directory"] == "comfyui_shotmill"
    root = integrations / lock["directory"]
    files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
    }
    assert set(files) == set(lock["files"]), "Bridge dependency file set changed without upgrade"
    for name, path in files.items():
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        assert hashlib.sha256(content).hexdigest() == lock["files"][name], (
            f"{name}: edit the independent Bridge repository, then upgrade the pinned snapshot"
        )
