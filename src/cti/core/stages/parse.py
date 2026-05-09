"""Parse stage: drives a Parser; raw bytes -> record dicts."""

from __future__ import annotations

from typing import Any

from cti.core.errors import PermanentError
from cti.core.interfaces import Parser
from cti.core.models import RawPayload, RunContext
from cti.core.queue import StageQueue
from cti.obs.metrics import PARSE_ERRORS


async def run_parse(
    parser: Parser,
    ctx: RunContext,
    inq: StageQueue[RawPayload],
    out: StageQueue[dict[str, Any]],
) -> None:
    try:
        async for payload in inq:
            try:
                async for record in parser.parse(payload, ctx):
                    await out.put(record)
            except PermanentError:
                PARSE_ERRORS.labels(source=ctx.source_id).inc()
                raise
    finally:
        await out.close()
