"""Process-local + (optional) Redis-backed concurrency limits."""

from __future__ import annotations

import asyncio


class PerSourceConcurrency:
    """Bounded semaphores per source. In-process only (one worker)."""

    def __init__(self) -> None:
        self._sems: dict[str, asyncio.Semaphore] = {}

    def get(self, source_id: str, max_parallelism: int) -> asyncio.Semaphore:
        sem = self._sems.get(source_id)
        if sem is None:
            sem = asyncio.Semaphore(max(1, max_parallelism))
            self._sems[source_id] = sem
        return sem


class GlobalConcurrency:
    """Global limit across all sources in this worker."""

    def __init__(self, max_concurrent: int = 50) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self) -> None:
        await self._sem.acquire()

    async def __aexit__(self, *_: object) -> None:
        self._sem.release()
