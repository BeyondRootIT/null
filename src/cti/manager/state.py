"""FeedRun state machine, persisted via SELECT … FOR UPDATE on `feed_runs`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cti.core.enums import RunState
from cti.core.errors import WatermarkConflict
from cti.persistence.models import FeedRunRow, SourceRow


async def open_run(
    session: AsyncSession, source_id: str, run_id: UUID
) -> tuple[FeedRunRow, dict[str, Any]]:
    """Insert PENDING row + return current watermark snapshot.

    Uses SELECT … FOR UPDATE on the source row to prevent two workers running
    the same source concurrently.
    """
    source = await session.get(SourceRow, source_id, with_for_update=True)
    if source is None:
        raise WatermarkConflict(f"source not registered: {source_id}")
    row = FeedRunRow(
        id=run_id,
        source_id=source_id,
        state=RunState.PENDING.value,
        started_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row, dict(source.watermark or {})


async def mark_running(session: AsyncSession, row: FeedRunRow) -> None:
    row.state = RunState.RUNNING.value
    await session.flush()


async def finalize_run(
    session: AsyncSession,
    row: FeedRunRow,
    state: RunState,
    *,
    fetched_bytes: int = 0,
    records_in: int = 0,
    records_out: int = 0,
    error: str | None = None,
    watermark: dict[str, Any] | None = None,
    raw_uri: str | None = None,
) -> None:
    row.state = state.value
    row.finished_at = datetime.now(UTC)
    row.fetched_bytes = fetched_bytes
    row.records_in = records_in
    row.records_out = records_out
    row.error = error
    row.watermark = watermark or {}
    row.raw_uri = raw_uri
    if state == RunState.SUCCESS and watermark is not None:
        source = await session.get(SourceRow, row.source_id, with_for_update=True)
        if source is not None:
            source.watermark = watermark
    await session.flush()
