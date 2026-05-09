"""`cti run-once <source_id>` — execute a feed run synchronously in this process."""

from __future__ import annotations

import asyncio
import json

import typer

from cti.config.schema import get_settings
from cti.manager.circuit_breaker import BreakerRegistry
from cti.manager.concurrency import GlobalConcurrency, PerSourceConcurrency
from cti.manager.registry import SourceRegistry
from cti.manager.runner import FeedRunner
from cti.obs.logging import configure
from cti.persistence.db import dispose, init_engine


def run_once(source_id: str) -> None:
    """Execute the named source's pipeline once, synchronously."""

    async def _go() -> None:
        settings = get_settings()
        configure(settings.obs.log_level, settings.obs.log_json)
        init_engine(settings.db.dsn)
        registry = SourceRegistry(settings.runtime.sources_file).load()
        source = registry.get(source_id)
        runner = FeedRunner(
            BreakerRegistry(),
            PerSourceConcurrency(),
            GlobalConcurrency(settings.runtime.global_concurrency),
        )
        try:
            outcome = await runner.execute(source)
        finally:
            await dispose()
        typer.echo(json.dumps({"source_id": source_id, "state": outcome.value}))

    asyncio.run(_go())
