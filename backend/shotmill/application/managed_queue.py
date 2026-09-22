import asyncio


class ManagedQueue(asyncio.Queue):
    """Re-evaluate persisted priority when a worker claims the next queued delivery."""

    def __init__(self, uow_factory):
        super().__init__()
        self.uow_factory = uow_factory

    def _get(self):
        with self.uow_factory() as uow:
            controls = uow.runtime_controls.all()
        # Unranked deliveries keep FIFO order, after explicitly ordered deliveries.
        index = min(
            range(len(self._queue)),
            key=lambda i: (
                controls[self._queue[i]].position
                if self._queue[i] in controls and controls[self._queue[i]].position is not None
                else float("inf"),
                i,
            ),
        )
        value = self._queue[index]
        del self._queue[index]
        return value
