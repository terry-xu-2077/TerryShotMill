from __future__ import annotations

from typing import Any


class _ShotMillIOBridgeBase:
    """A marker and pass-through; the Bridge API owns task input/output handling."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"*": ("*",)}}

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("*",)
    FUNCTION = "bridge"
    CATEGORY = "ShotMill/Bridge"

    def bridge(self, **kwargs: Any):
        # ComfyUI has already removed its execution-list wrapper. Payload lists,
        # tensors and bus values must pass through without conversion or copying.
        return tuple(kwargs.get(name) for name in self.RETURN_NAMES)


class ShotMillIOBridgeIn(_ShotMillIOBridgeBase):
    MAX_PORTS = 256
    RETURN_TYPES = ("*",) * MAX_PORTS
    RETURN_NAMES = tuple("*" if index == 0 else f"* {index + 1}" for index in range(MAX_PORTS))

    @classmethod
    def INPUT_TYPES(cls):
        # Bypassed or muted sources can disappear from the execution prompt.
        # Every declared output still needs its own value, including empty slots.
        return {"optional": {
            name: ("*", {"forceInput": True}) for name in cls.RETURN_NAMES
        }}


class ShotMillIOBridgeOut(_ShotMillIOBridgeBase):
    pass


NODE_CLASS_MAPPINGS = {
    "ShotMillIOBridgeIn": ShotMillIOBridgeIn,
    "ShotMillIOBridgeOut": ShotMillIOBridgeOut,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ShotMillIOBridgeIn": "ShotMill IO Bridge In",
    "ShotMillIOBridgeOut": "ShotMill IO Bridge Out",
}
