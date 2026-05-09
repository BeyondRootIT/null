"""Dedup stage — *advisory* bloom-filter cache to skip DB roundtrips.

CRITICAL: Bloom filters have false positives. A bloom-positive only causes us to
*also* check the DB; the authoritative dedup is the unique constraint on
(type, value) in Postgres. NEVER drop on bloom-positive alone.
"""

from __future__ import annotations

from typing import Any, Protocol

from cti.core.models import Indicator, RunContext
from cti.core.queue import StageQueue


class _RedisBloom(Protocol):
    async def execute_command(self, *args: object) -> object: ...


class BloomCache:
    """Wrapper around Redis bloom (BF.ADD / BF.EXISTS) with safe fallback."""

    def __init__(self, redis: _RedisBloom | None, key: str = "cti:bloom:run"):
        self._redis = redis
        self._key = key

    async def add(self, ind_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.execute_command("BF.ADD", self._key, ind_id)
        except Exception:  # noqa: BLE001 — bloom is advisory; never fail the run
            pass

    async def exists(self, ind_id: str) -> bool:
        if self._redis is None:
            return False
        try:
            res = await self._redis.execute_command("BF.EXISTS", self._key, ind_id)
            return bool(res)
        except Exception:  # noqa: BLE001
            return False


async def run_dedup(
    bloom: BloomCache | None,
    ctx: RunContext,
    inq: StageQueue[tuple[Indicator, dict[str, Any]]],
    out: StageQueue[tuple[Indicator, dict[str, Any]]],
) -> None:
    try:
        async for indicator, raw in inq:
            if bloom is not None:
                # Advisory only: we still pass through to DB UPSERT which is authoritative.
                # Bloom-positives are forwarded; bloom is just a perf hint.
                await bloom.add(str(indicator.id))
            await out.put((indicator, raw))
    finally:
        await out.close()
