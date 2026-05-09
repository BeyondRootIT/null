"""Pipeline composition: run all stages concurrently with backpressure + cancellation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cti.core.enums import RunState
from cti.core.errors import CTIError, PermanentError
from cti.core.interfaces import Connector, Enricher, Parser, Publisher
from cti.core.models import Indicator, Observation, RawPayload, RunContext, RunResult
from cti.core.queue import StageQueue
from cti.core.stages.dedup import BloomCache, run_dedup
from cti.core.stages.enrich import run_enrich
from cti.core.stages.fetch import run_fetch
from cti.core.stages.normalize import NormalizeConfig, run_normalize
from cti.core.stages.parse import run_parse
from cti.core.stages.persist import run_persist
from cti.core.stages.publish import run_publish
from cti.security.archive import RawArchive


@dataclass
class PipelineSpec:
    connector: Connector
    parser: Parser
    enrichers: list[Enricher]
    canonical_publisher: Publisher
    extra_publishers: list[Publisher] = field(default_factory=list)
    normalize: NormalizeConfig = field(default_factory=lambda: NormalizeConfig())
    archive: RawArchive | None = None
    bloom: BloomCache | None = None
    queue_maxsize: int = 1000
    batch_size: int = 500


class Pipeline:
    """Orchestrates the seven stages as concurrent tasks."""

    def __init__(self, spec: PipelineSpec) -> None:
        self.spec = spec

    async def run(self, ctx: RunContext) -> RunResult:
        spec = self.spec
        q_raw: StageQueue[RawPayload] = StageQueue("fetch", spec.queue_maxsize)
        q_records: StageQueue[dict] = StageQueue("parse", spec.queue_maxsize)
        q_indicators: StageQueue[tuple[Indicator, dict]] = StageQueue(
            "normalize", spec.queue_maxsize
        )
        q_enriched: StageQueue[tuple[Indicator, dict]] = StageQueue("enrich", spec.queue_maxsize)
        q_dedup: StageQueue[tuple[Indicator, dict]] = StageQueue("dedup", spec.queue_maxsize)
        q_persist: StageQueue[tuple[Indicator, Observation]] = StageQueue(
            "persist", spec.queue_maxsize
        )

        started = datetime.now(UTC)
        state = RunState.SUCCESS
        error: str | None = None

        async with asyncio.TaskGroup() as tg:
            tg.create_task(run_fetch(spec.connector, ctx, q_raw, spec.archive), name="fetch")
            tg.create_task(run_parse(spec.parser, ctx, q_raw, q_records), name="parse")
            tg.create_task(
                run_normalize(spec.normalize, ctx, q_records, q_indicators), name="normalize"
            )
            tg.create_task(run_enrich(spec.enrichers, ctx, q_indicators, q_enriched), name="enrich")
            tg.create_task(run_dedup(spec.bloom, ctx, q_enriched, q_dedup), name="dedup")
            tg.create_task(
                run_persist(
                    spec.canonical_publisher, ctx, q_dedup, q_persist, spec.batch_size
                ),
                name="persist",
            )
            tg.create_task(
                run_publish(spec.extra_publishers, ctx, q_persist, spec.batch_size),
                name="publish",
            )

        finished = datetime.now(UTC)
        return RunResult(
            run_id=ctx.run_id,
            source_id=ctx.source_id,
            state=state,
            started_at=started,
            finished_at=finished,
            error=error,
            watermark=ctx.watermark,
            raw_uri=ctx.raw_uri,
        )


def _flatten(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        out: list[BaseException] = []
        for sub in exc.exceptions:
            out.extend(_flatten(sub))
        return out
    return [exc]


async def run_with_outcome(spec: PipelineSpec, ctx: RunContext) -> RunResult:
    """Wrap Pipeline.run, mapping exceptions to PARTIAL/FAILED outcomes."""
    started = datetime.now(UTC)
    state: RunState
    error: str | None = None
    try:
        return await Pipeline(spec).run(ctx)
    except BaseException as exc:  # noqa: BLE001
        flat = _flatten(exc)
        if any(isinstance(e, PermanentError) for e in flat):
            state = RunState.FAILED
        elif any(isinstance(e, CTIError) for e in flat):
            state = RunState.PARTIAL
        else:
            raise
        error = "; ".join(str(e) for e in flat if isinstance(e, CTIError))
    return RunResult(
        run_id=ctx.run_id,
        source_id=ctx.source_id,
        state=state,
        started_at=started,
        finished_at=datetime.now(UTC),
        error=error,
        watermark=ctx.watermark,
        raw_uri=ctx.raw_uri,
    )
