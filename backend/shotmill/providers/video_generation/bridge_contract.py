"""Provider-owned compatibility policy; never inferred from a package version."""

from copy import deepcopy
from typing import Any

from shotmill.errors import ShotMillError

APPLICATION_CONTRACT = {"name": "shotmill.video", "version": 1}
BASE_CAPABILITIES = (
    "workflowSnapshot", "preflight", "idempotentSubmit", "assetUpload",
    "resultDownload", "resultSha256", "cancelSubmission",
)
REQUIRED_CAPABILITIES = (*BASE_CAPABILITIES, "durableCompletion")


def checked_bridge_agreement(value: Any) -> dict[str, Any]:
    """Read previously frozen agreements without imposing newer admission rules."""
    valid = isinstance(value, dict) and set(value) == {
        "protocolVersion", "apiPrefix", "applicationContract", "requiredCapabilities",
    }
    if valid:
        contract, capabilities = value["applicationContract"], value["requiredCapabilities"]
        valid = (
            type(value["protocolVersion"]) is int and value["protocolVersion"] == 1
            and value["apiPrefix"] == "/terryflow/v1"
            and isinstance(contract, dict) and contract == APPLICATION_CONTRACT
            and type(contract.get("version")) is int
            and isinstance(capabilities, list)
            and all(isinstance(item, str) for item in capabilities)
        )
        if valid:
            valid = len(set(capabilities)) == len(capabilities) and set(capabilities) in (
                set(BASE_CAPABILITIES), set(REQUIRED_CAPABILITIES),
            )
    if not valid:
        raise ShotMillError("BRIDGE_INCOMPATIBLE", "任务通信契约无效，不能继续执行。", 409)
    return deepcopy(value)


def negotiate_bridge(health: Any) -> dict[str, Any]:
    """Select the supported protocol and return a JSON-safe execution agreement.

    Called for new submissions only. Historical jobs retain their recorded
    agreement (or their legacy behavior), including during result recovery.
    Unknown future capabilities are harmless; missing required ones are not.
    """
    reason = None
    if not isinstance(health, dict) or health.get("ok") is not True:
        reason = "服务未返回有效的能力声明"
    elif health.get("package") != "ComfyUI-TerryFlowBridge":
        reason = "节点包不支持 Terry Flow Bridge 协议"
    elif not isinstance(health.get("protocolVersions"), list) or not any(
        type(version) is int and version == 1 for version in health["protocolVersions"]
    ):
        reason = "没有兼容的通信协议版本"
    else:
        contracts = health.get("applicationContracts")
        if not isinstance(contracts, list) or not any(
            isinstance(item, dict)
            and item.get("name") == APPLICATION_CONTRACT["name"]
            and type(item.get("version")) is int
            and item["version"] == APPLICATION_CONTRACT["version"]
            for item in contracts
        ):
            reason = "没有兼容的 ShotMill 视频契约"
        else:
            capabilities = health.get("capabilities")
            missing = [
                name for name in REQUIRED_CAPABILITIES
                if not isinstance(capabilities, dict) or capabilities.get(name) is not True
            ]
            if missing:
                reason = "缺少必要能力：" + ", ".join(missing)
    if reason:
        raise ShotMillError(
            "BRIDGE_INCOMPATIBLE", f"无法提交新任务：{reason}，请更新 Bridge。", 422,
        )
    return {
        "protocolVersion": 1,
        "apiPrefix": "/terryflow/v1",
        "applicationContract": deepcopy(APPLICATION_CONTRACT),
        "requiredCapabilities": list(REQUIRED_CAPABILITIES),
    }
