"""APScheduler service that enqueues `run_feed` arq jobs on each source's cron.

Single-replica in v0; backed by Postgres jobstore so the schedule recovers on
restart. `MaxInstances=1` per source prevents overlapping runs.
"""

from __future__ import annotations

import asyncio
import random
import signal

import structlog
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings as ArqRedisSettings

from cti.config.schema import get_settings
from cti.manager.registry import SourceConfig, SourceRegistry
from cti.obs.logging import configure as configure_logging
from cti.obs.metrics import REGISTRY
from cti.persistence.db import init_engine

log = structlog.get_logger(__name__)


def _sync_dsn(dsn: str) -> str:
    return dsn.replace("+asyncpg", "+psycopg2").replace("postgresql+psycopg2", "postgresql")


async def _enqueue(redis: ArqRedis, source: SourceConfig, queue: str) -> None:
    if source.jitter_seconds > 0:
        await asyncio.sleep(random.uniform(0, source.jitter_seconds))
    job = await redis.enqueue_job("run_feed", source.id, _queue_name=queue)
    log.info(
        "scheduler.enqueued",
        source=source.id,
        job_id=getattr(job, "job_id", None),
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.obs.log_level, settings.obs.log_json)
    init_engine(settings.db.dsn)
    registry = SourceRegistry(settings.runtime.sources_file).load()
    redis = await create_pool(ArqRedisSettings.from_dsn(settings.redis.url))

    jobstore = SQLAlchemyJobStore(url=_sync_dsn(settings.db.dsn), tablename="apscheduler_jobs")
    scheduler = AsyncIOScheduler(jobstores={"default": jobstore})
    queue = settings.runtime.arq_queue

    for source in registry.enabled():
        scheduler.add_job(
            _enqueue,
            trigger=CronTrigger.from_crontab(source.schedule),
            args=[redis, source, queue],
            id=f"feed:{source.id}",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            misfire_grace_time=300,
        )

    scheduler.start()
    log.info("scheduler.started", sources=len(registry.enabled()), registry=len(REGISTRY._names_to_collectors))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    scheduler.shutdown(wait=False)
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
