"""arq worker definition: executes `run_feed` jobs.

`run_feed(source_id)` is a fire-and-forget enqueued job. The worker holds a
single FeedRunner instance per process and the SourceRegistry is loaded once
at startup.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from arq.connections import RedisSettings as ArqRedisSettings

from cti.config.schema import get_settings
from cti.manager.circuit_breaker import BreakerRegistry
from cti.manager.concurrency import GlobalConcurrency, PerSourceConcurrency
from cti.manager.registry import SourceRegistry
from cti.manager.runner import FeedRunner
from cti.obs.logging import bind_run_context, clear_run_context, configure as configure_logging
from cti.persistence.db import init_engine

log = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.obs.log_level, settings.obs.log_json)
    init_engine(settings.db.dsn, pool_size=settings.db.pool_size)
    registry = SourceRegistry(settings.runtime.sources_file).load()
    ctx["registry"] = registry
    ctx["runner"] = FeedRunner(
        BreakerRegistry(),
        PerSourceConcurrency(),
        GlobalConcurrency(settings.runtime.global_concurrency),
    )
    log.info("worker.startup", sources=len(registry.all()))


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.shutdown")


async def run_feed(ctx: dict[str, Any], source_id: str) -> str:
    registry: SourceRegistry = ctx["registry"]
    runner: FeedRunner = ctx["runner"]
    cfg = registry.get(source_id)
    bind_run_context(run_id=ctx["job_id"], source_id=source_id)
    try:
        outcome = await runner.execute(cfg)
        log.info("run.complete", source=source_id, state=outcome.value)
        return outcome.value
    finally:
        clear_run_context()


def _redis_settings() -> ArqRedisSettings:
    url = os.environ.get("CTI_REDIS_URL", "redis://redis:6379/0")
    return ArqRedisSettings.from_dsn(url)


class WorkerSettings:
    """`arq cti.manager.worker.WorkerSettings` boots the worker."""

    functions = [run_feed]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    queue_name = os.environ.get("CTI_RUN_ARQ_QUEUE", "cti:queue")
    max_jobs = int(os.environ.get("CTI_WORKER_MAX_JOBS", "10"))
    job_timeout = int(os.environ.get("CTI_WORKER_JOB_TIMEOUT", "1800"))
    keep_result = 3600
