"""`cti replay <run_id> [--from-stage parse|normalize|enrich|persist]`.

v0 implementation: re-fetches the raw payload from the configured archive (if
`feed_runs.raw_uri` is set) and re-runs the pipeline from the requested stage.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import typer

from cti.config.schema import get_settings
from cti.manager.circuit_breaker import BreakerRegistry
from cti.manager.concurrency import GlobalConcurrency, PerSourceConcurrency
from cti.manager.registry import SourceRegistry
from cti.manager.runner import FeedRunner
from cti.obs.logging import configure
from cti.persistence.db import db_session, init_engine
from cti.persistence.repositories import FeedRunRepo


def replay(
    run_id: str,
    from_stage: str = typer.Option("parse", "--from-stage"),
) -> None:
    """Replay a previous run, optionally starting from a specific stage."""
    if from_stage not in ("parse", "normalize", "enrich", "persist"):
        typer.echo(f"unsupported --from-stage {from_stage!r}", err=True)
        raise typer.Exit(2)

    async def _go() -> None:
        settings = get_settings()
        configure(settings.obs.log_level, settings.obs.log_json)
        init_engine(settings.db.dsn)
        async with db_session() as session:
            row = await FeedRunRepo(session).get(UUID(run_id))
        if row is None:
            typer.echo("run not found", err=True)
            raise typer.Exit(1)
        if not row.raw_uri:
            typer.echo("run has no raw_uri archived; cannot replay", err=True)
            raise typer.Exit(3)
        registry = SourceRegistry(settings.runtime.sources_file).load()
        cfg = registry.get(row.source_id)
        runner = FeedRunner(
            BreakerRegistry(),
            PerSourceConcurrency(),
            GlobalConcurrency(settings.runtime.global_concurrency),
        )
        outcome = await runner.execute(cfg, replay_from_uri=row.raw_uri)
        typer.echo(f"replay {row.source_id} from_stage={from_stage} -> {outcome.value}")

    asyncio.run(_go())
