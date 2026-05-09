"""Per-host async token-bucket rate limiter.

Optionally backed by Redis for cross-worker fairness; falls back to in-process
bucket per (worker, host) when Redis is not provided.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass
class _Bucket:
    capacity: float
    rate: float
    tokens: float
    updated_at: float


class _RedisLike(Protocol):
    async def eval(self, script: str, numkeys: int, *args: str) -> object: ...


class TokenBucket:
    """Per-key async token bucket. `key` is typically the URL host."""

    # ARGV[1]=now, ARGV[2]=rate, ARGV[3]=capacity, ARGV[4]=cost
    _LUA = """
    local b = redis.call('HMGET', KEYS[1], 't', 'u')
    local tokens = tonumber(b[1])
    local updated = tonumber(b[2])
    local now = tonumber(ARGV[1])
    local rate = tonumber(ARGV[2])
    local cap = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])
    if tokens == nil then tokens = cap; updated = now end
    local delta = math.max(0, now - updated)
    tokens = math.min(cap, tokens + delta * rate)
    local allowed = 0
    if tokens >= cost then tokens = tokens - cost; allowed = 1 end
    redis.call('HMSET', KEYS[1], 't', tokens, 'u', now)
    redis.call('EXPIRE', KEYS[1], 3600)
    return {allowed, tostring(tokens)}
    """

    def __init__(
        self,
        rate_per_sec: float,
        burst: float | None = None,
        redis: _RedisLike | None = None,
        prefix: str = "cti:rl:",
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        self.rate = rate_per_sec
        self.burst = burst if burst is not None else max(1.0, rate_per_sec)
        self._redis = redis
        self._prefix = prefix
        self._local: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str, cost: float = 1.0) -> None:
        """Block until `cost` tokens are available for `key`."""
        while True:
            wait = await self._try(key, cost)
            if wait <= 0:
                return
            await asyncio.sleep(wait)

    async def _try(self, key: str, cost: float) -> float:
        if self._redis is not None:
            return await self._try_redis(key, cost)
        return await self._try_local(key, cost)

    async def _try_local(self, key: str, cost: float) -> float:
        async with self._lock:
            now = time.monotonic()
            b = self._local.get(key)
            if b is None:
                b = _Bucket(self.burst, self.rate, self.burst, now)
                self._local[key] = b
            elapsed = max(0.0, now - b.updated_at)
            b.tokens = min(self.burst, b.tokens + elapsed * self.rate)
            b.updated_at = now
            if b.tokens >= cost:
                b.tokens -= cost
                return 0.0
            return (cost - b.tokens) / self.rate

    async def _try_redis(self, key: str, cost: float) -> float:
        assert self._redis is not None
        now = time.time()
        result = await self._redis.eval(
            self._LUA,
            1,
            f"{self._prefix}{key}",
            f"{now}",
            f"{self.rate}",
            f"{self.burst}",
            f"{cost}",
        )
        allowed, tokens = result  # type: ignore[misc]
        if int(allowed) == 1:
            return 0.0
        return max(0.0, (cost - float(tokens)) / self.rate)


class HostRateLimiter:
    """Group of TokenBuckets keyed by hostname, with per-host overrides."""

    def __init__(
        self,
        default_rps: float = 5.0,
        overrides: Mapping[str, float] | None = None,
        redis: _RedisLike | None = None,
    ) -> None:
        self._default = TokenBucket(default_rps, redis=redis, prefix="cti:rl:default:")
        self._buckets: dict[str, TokenBucket] = {
            host: TokenBucket(rps, redis=redis, prefix=f"cti:rl:{host}:")
            for host, rps in (overrides or {}).items()
        }

    async def acquire(self, host: str, cost: float = 1.0) -> None:
        bucket = self._buckets.get(host, self._default)
        await bucket.acquire(host, cost)
