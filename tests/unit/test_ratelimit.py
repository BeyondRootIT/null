from __future__ import annotations

import time

import pytest

from cti.core.ratelimit import HostRateLimiter


@pytest.mark.asyncio
async def test_token_bucket_throttles():
    limiter = HostRateLimiter(default_rps=10.0)
    start = time.monotonic()
    for _ in range(15):
        await limiter.acquire("h")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.4
