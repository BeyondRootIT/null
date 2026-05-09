"""Per-source 3-state circuit breaker (closed → open → half-open)."""

from __future__ import annotations

import asyncio
import time
from enum import StrEnum

from cti.core.errors import CircuitOpen
from cti.manager.registry import CircuitPolicy


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, source_id: str, policy: CircuitPolicy) -> None:
        self.source_id = source_id
        self.policy = policy
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def before(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._state == CircuitState.OPEN:
                if now - self._opened_at >= self.policy.recovery_seconds:
                    self._state = CircuitState.HALF_OPEN
                else:
                    self._record_metric()
                    raise CircuitOpen(f"circuit open for source {self.source_id}")
            self._record_metric()

    async def on_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED
            self._record_metric()

    async def on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if (
                self._state == CircuitState.HALF_OPEN
                or self._failures >= self.policy.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
            self._record_metric()

    def _record_metric(self) -> None:
        try:
            from cti.obs.metrics import CIRCUIT_STATE

            value = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}[
                self._state
            ]
            CIRCUIT_STATE.labels(source=self.source_id).set(value)
        except ImportError:
            pass


class BreakerRegistry:
    """Process-local breaker store keyed by source_id."""

    def __init__(self) -> None:
        self._store: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get(self, source_id: str, policy: CircuitPolicy) -> CircuitBreaker:
        async with self._lock:
            breaker = self._store.get(source_id)
            if breaker is None:
                breaker = CircuitBreaker(source_id, policy)
                self._store[source_id] = breaker
            return breaker
