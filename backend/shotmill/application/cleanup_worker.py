import asyncio
import logging

from shotmill.application.permanent_delete_service import PermanentDeleteService

logger = logging.getLogger(__name__)


class CleanupWorker:
    def __init__(self, service: PermanentDeleteService, interval: float = 15):
        self.service = service
        self.interval = interval
        self.stopping = asyncio.Event()
        self.task: asyncio.Task | None = None

    async def start(self):
        self.stopping.clear()
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        self.stopping.set()
        if self.task is not None:
            await self.task
            self.task = None

    async def _run(self):
        while not self.stopping.is_set():
            try:
                await asyncio.to_thread(self.service.cleanup_pending)
            except Exception:
                logger.exception("Deferred media cleanup failed; will retry")
            try:
                await asyncio.wait_for(self.stopping.wait(), self.interval)
            except TimeoutError:
                pass
