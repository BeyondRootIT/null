"""Persist stage — drives the canonical (Postgres) publisher in batches.

This stage is the **durability fence**: anything that has passed here is durable
in Postgres via idempotent UPSERT on indicator_uuid.
"""

from __future__ import annotations

from typing import Any

from cti.core.interfaces import Publisher
from cti.core.models import Indicator, Observation, RunContext
from cti.core.queue import StageQueue
from cti.obs.metrics import RECORDS_OUT

DEFAULT_BATCH_SIZE = 500


async def run_persist(
    publisher: Publisher,
    ctx: RunContext,
    inq: StageQueue[tuple[Indicator, dict[str, Any]]],
    out: StageQueue[tuple[Indicator, Observation]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    batch: list[tuple[Indicator, Observation]] = []

    async def flush() -> None:
        if not batch:
            return
        await publisher.publish(batch, ctx)
        RECORDS_OUT.labels(source=ctx.source_id, publisher="postgres").inc(len(batch))
        for pair in batch:
            await out.put(pair)
        batch.clear()

    try:
        async for indicator, raw in inq:
            obs = Observation(
                indicator_id=indicator.id,
                source_id=ctx.source_id,
                feed_run_id=ctx.run_id,
                tlp=indicator.tlp,
                confidence=indicator.confidence,
                raw=raw,
            )
            batch.append((indicator, obs))
            if len(batch) >= batch_size:
                await flush()
        await flush()
    finally:
        await out.close()
