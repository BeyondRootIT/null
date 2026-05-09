"""Publish stage — fan-out to additional publishers (Kafka, webhook, …).

The canonical Postgres publisher runs in `persist`; this stage handles
*additional* downstream publishers configured for the source. TLP-aware:
publishers may refuse incompatible TLP and the indicator is dropped for them.
"""

from __future__ import annotations

from cti.core.errors import TLPViolation
from cti.core.interfaces import Publisher
from cti.core.models import Indicator, Observation, RunContext
from cti.core.queue import StageQueue
from cti.obs.metrics import DROPPED, RECORDS_OUT

DEFAULT_BATCH_SIZE = 500


async def run_publish(
    publishers: list[Publisher],
    ctx: RunContext,
    inq: StageQueue[tuple[Indicator, Observation]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    if not publishers:
        async for _ in inq:
            pass
        return

    batches: dict[str, list[tuple[Indicator, Observation]]] = {p.name: [] for p in publishers}

    async def flush(publisher: Publisher) -> None:
        batch = batches[publisher.name]
        if not batch:
            return
        try:
            await publisher.publish(batch, ctx)
            RECORDS_OUT.labels(source=ctx.source_id, publisher=publisher.name).inc(len(batch))
        except TLPViolation:
            DROPPED.labels(source=ctx.source_id, reason=f"tlp:{publisher.name}").inc(len(batch))
        batch.clear()

    async for indicator, observation in inq:
        for publisher in publishers:
            batches[publisher.name].append((indicator, observation))
            if len(batches[publisher.name]) >= batch_size:
                await flush(publisher)
    for publisher in publishers:
        await flush(publisher)
