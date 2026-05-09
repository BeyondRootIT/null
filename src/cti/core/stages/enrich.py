"""Enrich stage: chains Enrichers; any returning None drops the indicator."""

from __future__ import annotations

from typing import Any

from cti.core.interfaces import Enricher
from cti.core.models import Indicator, RunContext
from cti.core.queue import StageQueue
from cti.obs.metrics import DROPPED


async def run_enrich(
    enrichers: list[Enricher],
    ctx: RunContext,
    inq: StageQueue[tuple[Indicator, dict[str, Any]]],
    out: StageQueue[tuple[Indicator, dict[str, Any]]],
) -> None:
    try:
        async for indicator, raw in inq:
            current: Indicator | None = indicator
            for enricher in enrichers:
                if current is None:
                    break
                current = await enricher.enrich(current, ctx)
            if current is None:
                DROPPED.labels(source=ctx.source_id, reason="enricher").inc()
                continue
            await out.put((current, raw))
    finally:
        await out.close()
