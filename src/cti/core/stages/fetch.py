"""Fetch stage: drives a Connector and emits RawPayloads.

Side effect: archives raw bytes to the configured object store (default-on)
and stamps `ctx.raw_uri` so replay can skip Fetch.
"""

from __future__ import annotations

from cti.core.interfaces import Connector
from cti.core.models import RawPayload, RunContext
from cti.core.queue import StageQueue
from cti.obs.metrics import FETCH_BYTES, FETCH_SECONDS, RECORDS_IN
from cti.security.archive import RawArchive


async def run_fetch(
    connector: Connector,
    ctx: RunContext,
    out: StageQueue[RawPayload],
    archive: RawArchive | None,
) -> None:
    with FETCH_SECONDS.labels(source=ctx.source_id).time():
        async for payload in connector.fetch(ctx):
            FETCH_BYTES.labels(source=ctx.source_id).inc(len(payload.body))
            RECORDS_IN.labels(source=ctx.source_id, stage="fetch").inc()
            if archive is not None:
                ctx.raw_uri = await archive.put(ctx, payload)
            await out.put(payload)
    await out.close()
