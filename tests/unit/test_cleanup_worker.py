import asyncio
import threading

from shotmill.application.cleanup_worker import CleanupWorker


def test_cleanup_worker_retries_transient_failure_and_stops():
    class Service:
        calls = 0
        recovered = threading.Event()

        def cleanup_pending(self):
            self.calls += 1
            if self.calls == 1:
                raise OSError("transient database failure")
            self.recovered.set()

    service = Service()

    async def scenario():
        worker = CleanupWorker(service, interval=0.001)
        await worker.start()
        try:
            assert await asyncio.to_thread(service.recovered.wait, 2)
        finally:
            await worker.stop()
        assert worker.task is None
        assert service.calls >= 2

    asyncio.run(scenario())
