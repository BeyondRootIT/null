"""Tenacity-based retry helper. Retries TransientError + RateLimited only."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from cti.core.errors import RateLimited, TransientError
from cti.manager.registry import RetryPolicy

T = TypeVar("T")


async def with_retry(policy: RetryPolicy, fn: Callable[[], Awaitable[T]]) -> T:
    retrying = AsyncRetrying(
        stop=stop_after_attempt(policy.max_attempts),
        wait=wait_exponential_jitter(initial=policy.initial_seconds, max=policy.max_seconds),
        retry=retry_if_exception_type((TransientError, RateLimited)),
        reraise=True,
    )
    try:
        async for attempt in retrying:
            with attempt:
                return await fn()
    except RetryError as exc:
        raise exc.last_attempt.exception() or exc
    raise RuntimeError("unreachable")
