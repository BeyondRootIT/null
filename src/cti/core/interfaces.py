"""Plugin ABCs. The four extension points of the framework.

Plugin authors typically subclass `SyncParser`, `SyncEnricher`, or `HttpConnectorBase`
(see `cti.plugins.connectors.http_base`) rather than these async ABCs directly.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from cti.core.models import Indicator, Observation, RawPayload, RunContext

C = TypeVar("C", bound=BaseModel)


class Plugin(ABC, Generic[C]):
    """Common base for all plugin kinds."""

    name: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]

    def __init__(self, config: C) -> None:
        self.config: C = config

    async def aclose(self) -> None:
        """Override to release resources (HTTP clients, file handles, …)."""

    def metrics(self) -> Iterable[tuple[str, str]]:
        """Optional: declare metric names this plugin emits.

        Yielded as `(metric_suffix, help_text)`. The framework auto-prefixes
        `cti_plugin_<name>_` to avoid collisions.
        """
        return ()


class Connector(Plugin[C]):
    """Pulls raw bytes from a remote source. Stateless w.r.t. parsing."""

    @abstractmethod
    def fetch(self, ctx: RunContext) -> AsyncIterator[RawPayload]:  # type: ignore[misc]
        """Yield 1..N raw payloads (paginated APIs may yield many)."""


class Parser(Plugin[C]):
    """Turns RawPayload into untyped record dicts."""

    @abstractmethod
    def parse(  # type: ignore[misc]
        self, payload: RawPayload, ctx: RunContext
    ) -> AsyncIterator[dict[str, Any]]:
        ...


class Normalizer(Plugin[C]):
    """Maps a record dict to one or more Indicator candidates.

    This is normally configuration-driven via the built-in normalizer
    (`cti.core.stages.normalize`), but a custom Normalizer plugin lets you
    handle exotic feeds without writing a Parser+Connector pair.
    """

    @abstractmethod
    def normalize(  # type: ignore[misc]
        self, record: dict[str, Any], ctx: RunContext
    ) -> AsyncIterator[Indicator]:
        ...


class Enricher(Plugin[C]):
    """Pure (idempotent) function over an Indicator. Returning None drops it."""

    @abstractmethod
    async def enrich(self, ind: Indicator, ctx: RunContext) -> Indicator | None: ...


class Publisher(Plugin[C]):
    """Sink for finalized indicators + observations."""

    @abstractmethod
    async def publish(
        self,
        batch: list[tuple[Indicator, Observation]],
        ctx: RunContext,
    ) -> None: ...


# --- Sync-bridge base classes ----------------------------------------------------
# Plugin authors inheriting these write sync code; the framework wraps them in
# `asyncio.to_thread` so CPU-bound work doesn't block the event loop.


class SyncParser(Parser[C]):
    """Inherit and implement `parse_sync` (sync generator)."""

    @abstractmethod
    def parse_sync(self, payload: RawPayload, ctx: RunContext) -> Iterable[dict[str, Any]]: ...

    async def parse(  # type: ignore[override]
        self, payload: RawPayload, ctx: RunContext
    ) -> AsyncIterator[dict[str, Any]]:
        records = await asyncio.to_thread(lambda: list(self.parse_sync(payload, ctx)))
        for record in records:
            yield record


class SyncEnricher(Enricher[C]):
    """Inherit and implement `enrich_sync`."""

    @abstractmethod
    def enrich_sync(self, ind: Indicator, ctx: RunContext) -> Indicator | None: ...

    async def enrich(self, ind: Indicator, ctx: RunContext) -> Indicator | None:
        return await asyncio.to_thread(self.enrich_sync, ind, ctx)
