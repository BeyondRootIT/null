"""Canonical Postgres publisher: idempotent UPSERT + observation insert."""

from __future__ import annotations

from pydantic import BaseModel

from cti.core.interfaces import Publisher
from cti.core.models import Indicator, Observation, RunContext
from cti.persistence.db import db_session
from cti.persistence.repositories import IndicatorRepo


class PostgresPublisherConfig(BaseModel):
    pass


class PostgresPublisher(Publisher[PostgresPublisherConfig]):
    name = "postgres"
    config_model = PostgresPublisherConfig

    async def publish(
        self,
        batch: list[tuple[Indicator, Observation]],
        ctx: RunContext,
    ) -> None:
        if not batch:
            return
        async with db_session() as session:
            await IndicatorRepo(session).upsert_batch(batch)
            await session.commit()
