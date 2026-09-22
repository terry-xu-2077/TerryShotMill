from __future__ import annotations

import math
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
        return {"optional": {name: ("*", {"forceInput": True}) for name in cls.RETURN_NAMES}}


class ShotMillIOBridgeOut(_ShotMillIOBridgeBase):
    pass


class ShotMillResolutionSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "resolution": (["480p", "720p", "1080p"], {"default": "720p"}),
                "aspect_ratio": (["16:9", "9:16", "1:1", "4:3", "3:4"],),
                "alignment": ("INT", {"default": 32, "min": 1, "max": 128}),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "select"
    CATEGORY = "ShotMill/Bridge"

    def select(self, resolution="720p", aspect_ratio="16:9", alignment=32):
        if resolution not in {"480p", "720p", "1080p"}:
            raise ValueError("Unsupported resolution")
        if aspect_ratio not in {"16:9", "9:16", "1:1", "4:3", "3:4"}:
            raise ValueError("Unsupported aspect ratio")
        if (
            isinstance(alignment, bool)
            or not isinstance(alignment, int)
            or not 1 <= alignment <= 128
        ):
            raise ValueError("Invalid pixel alignment")
        x, y = map(int, aspect_ratio.split(":"))
        short = int(resolution[:-1])
        scale = short / min(x, y)
        return tuple(math.ceil(value * scale / alignment) * alignment for value in (x, y))


class ShotMillDurationSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seconds": ("FLOAT", {"default": 6.0, "min": 0.1, "max": 60, "step": 0.1}),
                "model": (["H3", "custom"], {"default": "H3"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1, "max": 240}),
                "frame_multiple": ("INT", {"default": 17, "min": 1, "max": 256}),
                "frame_offset": ("INT", {"default": 5, "min": 0, "max": 255}),
            }
        }

    RETURN_TYPES = ("INT", "FLOAT")
    RETURN_NAMES = ("length", "fps")
    FUNCTION = "select"
    CATEGORY = "ShotMill/Bridge"

    def select(self, seconds=6.0, model="H3", fps=24.0, frame_multiple=17, frame_offset=5):
        if isinstance(seconds, bool) or not math.isfinite(float(seconds)) or not 0 < seconds <= 60:
            raise ValueError("Seconds must be finite and in (0, 60]")
        if model == "H3":
            fps, frame_multiple, frame_offset = 24.0, 17, 5
        elif model != "custom":
            raise ValueError("Unsupported duration model")
        if not math.isfinite(fps) or not 1 <= fps <= 240:
            raise ValueError("Invalid frame rate")
        if not isinstance(frame_multiple, int) or not 1 <= frame_multiple <= 256:
            raise ValueError("Invalid frame multiple")
        if not isinstance(frame_offset, int) or not 0 <= frame_offset < frame_multiple:
            raise ValueError("Invalid frame offset")
        length = max(1, math.ceil((seconds * fps - frame_offset) / frame_multiple))
        # H3 permits its smallest 5-frame clip as well as longer 17n+5 clips.
        if frame_offset > 0:
            length = max(0, math.ceil((seconds * fps - frame_offset) / frame_multiple))
        return (length * frame_multiple + frame_offset, fps)


NODE_CLASS_MAPPINGS = {
    "ShotMillResolutionSelector": ShotMillResolutionSelector,
    "ShotMillDurationSelector": ShotMillDurationSelector,
    "ShotMillIOBridgeIn": ShotMillIOBridgeIn,
    "ShotMillIOBridgeOut": ShotMillIOBridgeOut,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ShotMillResolutionSelector": "ShotMill Bridge 分辨率选择器",
    "ShotMillDurationSelector": "ShotMill Bridge 秒数选择器",
    "ShotMillIOBridgeIn": "ShotMill IO Bridge In",
    "ShotMillIOBridgeOut": "ShotMill IO Bridge Out",
}
