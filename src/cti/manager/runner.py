"""FeedRunner — orchestrates a single feed run end-to-end.

Lifecycle:
    open_run (PENDING) → circuit_breaker → with_retry( pipeline.run ) → finalize_run
                                                       │
                                                       └── on PermanentError → DLQ
"""

from __future__ import annotations

from uuid import UUID, uuid4

import structlog

from cti.core.enums import RunState
from cti.core.errors import CircuitOpen, PermanentError
from cti.core.models import RunContext
from cti.core.pipeline import run_with_outcome
from cti.manager.circuit_breaker import BreakerRegistry
from cti.manager.concurrency import GlobalConcurrency, PerSourceConcurrency
from cti.manager.deadletter import record_dead_letter
from cti.manager.registry import SourceConfig
from cti.manager.retry import with_retry
from cti.manager.state import finalize_run, mark_running, open_run
from cti.persistence.db import db_session
from cti.plugins.builder import build_pipeline_spec

log = structlog.get_logger(__name__)


class FeedRunner:
    """Executes one feed run for one source. Stateless; reusable across calls."""

    def __init__(
        self,
        breakers: BreakerRegistry,
        per_source: PerSourceConcurrency,
        globals_: GlobalConcurrency,
    ) -> None:
        self._breakers = breakers
        self._per_source = per_source
        self._globals = globals_

    async def execute(
        self,
        source: SourceConfig,
        *,
        run_id: UUID | None = None,
        replay_from_uri: str | None = None,
    ) -> RunState:
        run_id = run_id or uuid4()
        breaker = await self._breakers.get(source.id, source.circuit)
        sem = self._per_source.get(source.id, source.max_parallelism)

        async with self._globals, sem:
            try:
                await breaker.before()
            except CircuitOpen:
                log.warning("circuit_open_skip", source=source.id, run=str(run_id))
                return RunState.FAILED

            spec = await build_pipeline_spec(source, replay_from_uri=replay_from_uri)
            try:
                async with db_session() as session:
                    row, watermark = await open_run(session, source.id, run_id)
                    await mark_running(session, row)
                    await session.commit()

                ctx = RunContext(
                    run_id=run_id, source_id=source.id, watermark=dict(watermark)
                )

                async def run_pipeline() -> object:
                    return await run_with_outcome(spec, ctx)

                result = await with_retry(source.retry, run_pipeline)

                async with db_session() as session:
                    row = await session.get(type(row), run_id)
                    assert row is not None
                    await finalize_run(
                        session,
                        row,
                        RunState(result.state),
                        records_in=result.records_in,
                        records_out=result.records_out,
                        fetched_bytes=result.fetched_bytes,
                        error=result.error,
                        watermark=result.watermark,
                        raw_uri=result.raw_uri,
                    )
                    await session.commit()

                if result.state == RunState.SUCCESS:
                    await breaker.on_success()
                else:
                    await breaker.on_failure()
                return RunState(result.state)

            except PermanentError as exc:
                await breaker.on_failure()
                async with db_session() as session:
                    await record_dead_letter(
                        session,
                        feed_run_id=run_id,
                        source_id=source.id,
                        payload=None,
                        error=exc,
                    )
                    await session.commit()
                log.error("permanent_failure", source=source.id, error=str(exc))
                return RunState.FAILED
            except Exception as exc:  # noqa: BLE001
                await breaker.on_failure()
                log.exception("transient_failure", source=source.id, error=str(exc))
                return RunState.FAILED
            finally:
                for plugin in (
                    spec.connector,
                    spec.parser,
                    spec.canonical_publisher,
                    *spec.enrichers,
                    *spec.extra_publishers,
                ):
                    try:
                        await plugin.aclose()
                    except Exception:  # noqa: BLE001
                        pass
