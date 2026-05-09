from __future__ import annotations

import pytest

from cti.core.errors import CircuitOpen
from cti.manager.circuit_breaker import CircuitBreaker, CircuitState
from cti.manager.registry import CircuitPolicy


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold():
    breaker = CircuitBreaker(
        "src", CircuitPolicy(failure_threshold=2, recovery_seconds=300)
    )
    await breaker.before()
    await breaker.on_failure()
    await breaker.before()
    await breaker.on_failure()
    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitOpen):
        await breaker.before()


@pytest.mark.asyncio
async def test_breaker_resets_on_success():
    breaker = CircuitBreaker("src", CircuitPolicy(failure_threshold=2))
    await breaker.before()
    await breaker.on_failure()
    await breaker.on_success()
    assert breaker.state == CircuitState.CLOSED
