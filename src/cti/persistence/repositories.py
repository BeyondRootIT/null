"""Narrow async repositories. Pipeline stages call these, not raw SQL."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cti.core.models import Indicator, Observation
from cti.persistence.models import (
    DeadLetterRow,
    FeedRunRow,
    IndicatorObservationRow,
    IndicatorRow,
    SourceRow,
)


class IndicatorRepo:
    """UPSERTs indicators + appends observations. Idempotent on `indicator_uuid`."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def upsert_batch(self, batch: list[tuple[Indicator, Observation]]) -> int:
        if not batch:
            return 0
        now = datetime.now(UTC)
        ind_rows = [
            {
                "id": ind.id,
                "type": ind.type.value,
                "value": ind.value,
                "pattern": ind.pattern,
                "confidence": ind.confidence,
                "severity": ind.severity.value,
                "tlp": ind.tlp.value,
                "tags": list(ind.tags),
                "first_seen_by_us": ind.first_seen_by_us,
                "last_seen_by_us": ind.last_seen_by_us,
                "valid_from": ind.valid_from,
                "valid_until": ind.valid_until,
                "schema_version": ind.schema_version,
            }
            for ind, _ in batch
        ]
        stmt = pg_insert(IndicatorRow).values(ind_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[IndicatorRow.id],
            set_={
                "last_seen_by_us": func.greatest(
                    IndicatorRow.last_seen_by_us, stmt.excluded.last_seen_by_us
                ),
                "confidence": func.greatest(
                    IndicatorRow.confidence, stmt.excluded.confidence
                ),
                "tags": stmt.excluded.tags,
            },
        )
        await self.s.execute(stmt)

        obs_rows = [
            {
                "indicator_id": obs.indicator_id,
                "source_id": obs.source_id,
                "feed_run_id": obs.feed_run_id,
                "observed_at": obs.observed_at or now,
                "tlp": obs.tlp.value,
                "confidence": obs.confidence,
                "raw": obs.raw,
                "schema_version": obs.schema_version,
            }
            for _, obs in batch
        ]
        await self.s.execute(IndicatorObservationRow.__table__.insert(), obs_rows)
        return len(batch)


class FeedRunRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def get(self, run_id: UUID) -> FeedRunRow | None:
        return await self.s.get(FeedRunRow, run_id)

    async def recent(self, source_id: str | None = None, limit: int = 50) -> list[FeedRunRow]:
        stmt = select(FeedRunRow).order_by(FeedRunRow.started_at.desc()).limit(limit)
        if source_id:
            stmt = stmt.where(FeedRunRow.source_id == source_id)
        result = await self.s.execute(stmt)
        return list(result.scalars().all())


class SourceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def upsert(
        self, source_id: str, name: str | None, plugin: str, config_hash: str, enabled: bool
    ) -> SourceRow:
        now = datetime.now(UTC)
        stmt = pg_insert(SourceRow).values(
            id=source_id,
            name=name,
            plugin=plugin,
            config_hash=config_hash,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[SourceRow.id],
            set_={
                "name": stmt.excluded.name,
                "plugin": stmt.excluded.plugin,
                "config_hash": stmt.excluded.config_hash,
                "enabled": stmt.excluded.enabled,
                "updated_at": now,
            },
        )
        await self.s.execute(stmt)
        result = await self.s.get(SourceRow, source_id)
        assert result is not None
        return result

    async def list(self) -> list[SourceRow]:
        result = await self.s.execute(select(SourceRow).order_by(SourceRow.id))
        return list(result.scalars().all())


class DeadLetterRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list(
        self, source_id: str | None = None, unreplayed_only: bool = True, limit: int = 100
    ) -> list[DeadLetterRow]:
        stmt = select(DeadLetterRow).order_by(DeadLetterRow.created_at.desc()).limit(limit)
        if source_id:
            stmt = stmt.where(DeadLetterRow.source_id == source_id)
        if unreplayed_only:
            stmt = stmt.where(DeadLetterRow.replayed_at.is_(None))
        result = await self.s.execute(stmt)
        return list(result.scalars().all())

    async def mark_replayed(self, dlq_id: int) -> None:
        row = await self.s.get(DeadLetterRow, dlq_id)
        if row is not None:
            row.replayed_at = datetime.now(UTC)


class IndicatorLookupRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def lookup(
        self, ind_type: str | None = None, value: str | None = None, limit: int = 100
    ) -> list[IndicatorRow]:
        stmt = select(IndicatorRow).order_by(IndicatorRow.last_seen_by_us.desc()).limit(limit)
        if ind_type:
            stmt = stmt.where(IndicatorRow.type == ind_type)
        if value:
            stmt = stmt.where(IndicatorRow.value == value)
        result = await self.s.execute(stmt)
        return list(result.scalars().all())

    async def get(self, indicator_id: UUID) -> IndicatorRow | None:
        return await self.s.get(IndicatorRow, indicator_id)


def aggregate_observations(_: Any) -> dict[str, Any]:
    """Placeholder for v0.1: cross-source TLP aggregation reads observations."""
    return {}
