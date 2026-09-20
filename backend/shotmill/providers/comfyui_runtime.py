from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class ComfyUIExecutionCoordinator:
    """Coordinates memory release when switching ComfyUI workload families."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_kind: str | None = None

    async def prepare(self, kind: str, client: httpx.AsyncClient, base_url: str) -> None:
        await self._lock.acquire()
        try:
            if self._last_kind is not None and self._last_kind != kind:
                response = await client.post(
                    f"{base_url}/shotmill/v1/runtime/prepare",
                    json={"kind": kind, "previousKind": self._last_kind},
                )
                response.raise_for_status()
                logger.info(
                    "Released ComfyUI models and memory before switching %s -> %s",
                    self._last_kind,
                    kind,
                )
            self._last_kind = kind
        except BaseException:
            self._lock.release()
            raise

    async def finish(self) -> None:
        self._lock.release()
