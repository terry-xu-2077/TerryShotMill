import asyncio
import hashlib
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from shotmill.domain.providers import VideoGenerationRequest
from shotmill.errors import ShotMillError
from shotmill.providers.video_generation.bridge_contract import (
    APPLICATION_CONTRACT,
    BASE_CAPABILITIES,
    REQUIRED_CAPABILITIES,
    checked_bridge_agreement,
    negotiate_bridge,
)
from shotmill.providers.video_generation.comfyui import ComfyUIVideoGenerationProvider


def health():
    return {
        "ok": True, "package": "ComfyUI-TerryFlowBridge", "version": "0.5.0",
        "protocolVersions": [1], "applicationContracts": [deepcopy(APPLICATION_CONTRACT)],
        "capabilities": dict.fromkeys(REQUIRED_CAPABILITIES, True),
    }


def test_agreement_is_independent_of_mutable_health_and_unknown_extensions():
    response = health()
    response["protocolVersions"].append(2)
    response["applicationContracts"].append({"name": "future", "version": 9})
    response["capabilities"]["future"] = True
    response["version"] = "99.0.0"
    agreement = negotiate_bridge(response)
    response["applicationContracts"][0]["version"] = 2
    assert agreement["applicationContract"] == {"name": "shotmill.video", "version": 1}
    assert agreement["protocolVersion"] == 1
    assert agreement["apiPrefix"] == "/terryflow/v1"
    assert agreement["requiredCapabilities"] == list(REQUIRED_CAPABILITIES)


@pytest.mark.parametrize("capability", REQUIRED_CAPABILITIES)
@pytest.mark.parametrize("value", [None, False, 1, "true"])
def test_each_required_capability_requires_explicit_boolean_true(capability, value):
    response = health()
    response["capabilities"][capability] = value
    with pytest.raises(ShotMillError, match=capability):
        negotiate_bridge(response)


@pytest.mark.parametrize("field,value", [
    ("ok", 1), ("package", "ComfyUI-ShotMill"),
    ("protocolVersions", [True]), ("protocolVersions", ["1"]),
    ("protocolVersions", [2]), ("protocolVersions", None),
    ("applicationContracts", [{"name": "generic", "version": 1}]),
    ("applicationContracts", [{"name": "shotmill.video", "version": True}]),
    ("applicationContracts", [{"name": "shotmill.video", "version": 2}]),
    ("applicationContracts", None), ("capabilities", None),
])
def test_incompatible_declarations_never_silently_select_legacy(field, value):
    response = health()
    response[field] = value
    with pytest.raises(ShotMillError) as failure:
        negotiate_bridge(response)
    assert failure.value.code == "BRIDGE_INCOMPATIBLE"


@pytest.mark.parametrize("response", [None, [], "ready", {}, {"ok": False}])
def test_malformed_health_is_a_user_facing_compatibility_error(response):
    with pytest.raises(ShotMillError):
        negotiate_bridge(response)


def test_new_profile_negotiates_before_preflight_and_freezes_agreement(bridge_snapshot):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        assert request.url.path.startswith("/terryflow/v1/")
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json=health())
        if request.url.path.endswith("/snapshot"):
            return httpx.Response(200, json={"snapshot": bridge_snapshot()})
        if request.url.path.endswith("/workflows"):
            return httpx.Response(200, json={"workflows": [{"id": "w.json", "inputs": []}]})
        assert request.url.path.endswith("/validate")
        return httpx.Response(200, json={"ok": True})

    root = ComfyUIVideoGenerationProvider(
        "http://bridge", Path("w.json"), transport=httpx.MockTransport(handler),
    )
    request = VideoGenerationRequest("j", "p", "t", "prompt", (), {})
    profile = root.capture_profile(request)
    profile.update(asyncio.run(root.bind_profile(profile).validate(request)))
    assert paths[0] == "/terryflow/v1/health"
    rebound = root.bind_profile(profile)
    assert rebound.bridge_agreement == negotiate_bridge(health())
    profile["bridgeAgreement"]["applicationContract"]["version"] = 99
    assert rebound.bridge_agreement["applicationContract"]["version"] == 1
    paths.clear()
    asyncio.run(rebound.validate(request))
    assert all(not path.endswith("/health") for path in paths)


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("digest", ["correct", "missing", "wrong"])
def test_provider_recovery_uses_frozen_protocol_without_health_or_submit(modern, digest):
    paths = []
    prefix = "/terryflow/v1" if modern else "/shotmill/v1"

    def handler(request):
        paths.append(request.url.path)
        assert request.method == "GET"
        if request.url.path == prefix + "/jobs/j":
            return httpx.Response(200, json={
                "status": "completed", "promptId": "remote",
                "results": [{"filename": "result.mp4"}],
            })
        assert request.url.path == prefix + "/results/j/files/0"
        headers = {} if digest == "missing" else {
            "x-content-sha256": hashlib.sha256(b"video").hexdigest()
            if digest == "correct" else "0" * 64,
        }
        return httpx.Response(200, content=b"video", headers=headers)

    root = ComfyUIVideoGenerationProvider(
        "http://bridge", Path("w.json"), transport=httpx.MockTransport(handler),
    )
    profile = root.capture_profile(VideoGenerationRequest("j", "p", "t", "", (), {}))
    if modern:
        profile["bridgeAgreement"] = negotiate_bridge(health())
    else:
        profile.pop("requireBridgeAgreement")
    restored = root.bind_profile(profile)
    if digest == "wrong" or modern and digest == "missing":
        with pytest.raises(ShotMillError) as failure:
            asyncio.run(restored.resume("j"))
        assert failure.value.code.startswith("COMFYUI_DOWNLOAD_CHECKSUM_")
    else:
        result = asyncio.run(restored.resume("j"))
        try:
            assert result.outputs[0].content.read() == b"video"
            assert result.outputs[0].metadata["transferVerified"] is (digest == "correct")
        finally:
            result.close()
    assert paths == [prefix + "/jobs/j", prefix + "/results/j/files/0"]


def test_incompatible_new_submission_stops_before_workflow_upload_or_post():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(404)

    provider = ComfyUIVideoGenerationProvider(
        "http://bridge", Path("w.json"), transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ShotMillError) as failure:
        asyncio.run(provider.generate(VideoGenerationRequest("j", "p", "t", "", (), {})))
    assert failure.value.code == "BRIDGE_INCOMPATIBLE"
    assert paths == ["/terryflow/v1/health"]


@pytest.mark.parametrize("agreement", [[], "invalid", {"requiredCapabilities": [None]}])
def test_malformed_persisted_agreement_is_not_a_legacy_fallback(agreement):
    provider = ComfyUIVideoGenerationProvider("http://bridge", Path("w.json"))
    profile = provider.capture_profile(VideoGenerationRequest("j", "p", "t", "", (), {}))
    profile["bridgeAgreement"] = agreement
    with pytest.raises(ShotMillError):
        provider.bind_profile(profile)


def test_new_profile_without_agreement_cannot_resume_by_legacy_routes():
    def unexpected(request):
        pytest.fail(f"Incomplete new profile must not access the server: {request.url}")

    provider = ComfyUIVideoGenerationProvider(
        "http://bridge", Path("w.json"), transport=httpx.MockTransport(unexpected),
    )
    profile = provider.capture_profile(VideoGenerationRequest("j", "p", "t", "", (), {}))
    with pytest.raises(ShotMillError) as failure:
        asyncio.run(provider.bind_profile(profile).resume("j"))
    assert failure.value.code == "BRIDGE_AGREEMENT_MISSING"


def test_older_frozen_agreement_remains_readable_when_new_admission_requires_more():
    old = negotiate_bridge(health())
    old["requiredCapabilities"] = list(BASE_CAPABILITIES)
    assert checked_bridge_agreement(old) == old
    server = health()
    server["capabilities"].pop("durableCompletion")
    with pytest.raises(ShotMillError, match="durableCompletion"):
        negotiate_bridge(server)
