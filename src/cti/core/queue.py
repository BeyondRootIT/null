"""Bounded async queue helpers for inter-stage backpressure + queue-depth metrics."""

from __future__ import annotations

import asyncio
from typing import Final, Generic, TypeVar

T = TypeVar("T")

DEFAULT_MAXSIZE: Final = 1000
SENTINEL: Final = object()


class StageQueue(Generic[T]):
    """`asyncio.Queue` wrapper that publishes a depth gauge and uses a sentinel for EOS.

    Producers call `put` then `close` once. Consumers iterate via `__aiter__`,
    which yields until the sentinel is received.
    """

    def __init__(self, name: str, maxsize: int = DEFAULT_MAXSIZE) -> None:
        self.name = name
        self._q: asyncio.Queue[object] = asyncio.Queue(maxsize=maxsize)
        self._closed = False

    async def put(self, item: T) -> None:
        await self._q.put(item)
        self._record_depth()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._q.put(SENTINEL)

    async def get(self) -> T | None:
        item = await self._q.get()
        self._record_depth()
        if item is SENTINEL:
            return None
        return item  # type: ignore[return-value]

    def qsize(self) -> int:
        return self._q.qsize()

    def _record_depth(self) -> None:
        try:
            from cti.obs.metrics import QUEUE_DEPTH

            QUEUE_DEPTH.labels(stage=self.name).set(self._q.qsize())
        except ImportError:
            pass

    def __aiter__(self) -> StageQueue[T]:
        return self

    async def __anext__(self) -> T:
        item = await self.get()
        if item is None:
            raise StopAsyncIteration
        return item
