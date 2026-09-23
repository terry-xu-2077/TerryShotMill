"""Read-only ComfyUI event telemetry, isolated from generation success/failure."""

import asyncio
import json
import math
import time
from urllib.parse import urlencode

from websockets.asyncio.client import connect


class StepProgress:
    def __init__(self, prompt_id, graph):
        self.prompt_id = prompt_id
        self.graph = graph
        self.node = None
        self.started = None
        self.sample = None
        self.history = []

    def consume(self, message, now=None):
        now = time.time() if now is None else now
        data = message.get("data", {})
        if data.get("prompt_id") != self.prompt_id:
            return None
        kind = message.get("type")
        if kind not in {"executing", "progress"}:
            return None
        node = data.get("node") or self.node
        if node is None:
            return None
        if node != self.node:
            if self.node is not None and self.started is not None:
                self.history.append({"stage": self.label(), "seconds": now - self.started})
            self.node, self.started, self.sample = node, now, None
        value, total, eta = None, None, None
        if kind == "progress":
            try:
                value, total = float(data["value"]), float(data["max"])
            except (KeyError, ValueError, TypeError):
                return None
            if (
                not math.isfinite(total)
                or not math.isfinite(value)
                or total <= 0
                or not 0 <= value <= total
            ):
                return None
            if self.sample and value > self.sample[0]:
                eta = (now - self.sample[1]) / (value - self.sample[0]) * (total - value)
            elif not self.sample:
                if value > 0 and now > self.started:
                    eta = (now - self.started) / value * (total - value)
                self.sample = (value, now)
        return {
            "stage": self.label(),
            "step": value,
            "total": total,
            "percent": value / total * 100 if total else None,
            "stageStartedAt": self.started,
            "measuredAt": now,
            "stageSeconds": max(0, now - self.started),
            "remainingSeconds": eta,
            "stages": self.history[-30:],
        }

    def label(self):
        name = self.graph.get(str(self.node), {}).get("class_type", "")
        if "sampl" in name.lower():
            return "采样生成"
        if "decode" in name.lower():
            return "解码画面"
        if "save" in name.lower():
            return "保存结果"
        if "load" in name.lower():
            return "加载模型或素材"
        if "encode" in name.lower() or "text" in name.lower():
            return "编码提示词与素材"
        return "处理画面与素材"


async def watch_progress(base_url, client_id, tracker, report):
    uri = base_url.replace("https://", "wss://").replace("http://", "ws://")
    uri += "/ws?" + urlencode({"clientId": client_id})
    while True:
        try:
            async with connect(uri, max_size=2**20, open_timeout=5) as socket:
                async for raw in socket:
                    if not isinstance(raw, str):
                        continue
                    try:
                        update = tracker.consume(json.loads(raw))
                    except (ValueError, TypeError, AttributeError):
                        continue
                    if update:
                        await report(update)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Telemetry loss must never fail or resubmit a video job.
            tracker.sample = None
            await asyncio.sleep(3)
