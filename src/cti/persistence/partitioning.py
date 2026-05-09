"""Monthly partition helper for `indicator_observations`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def _partition_bounds(year: int, month: int) -> tuple[str, str, str]:
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    name = f"indicator_observations_{year:04d}_{month:02d}"
    start = f"{year:04d}-{month:02d}-01"
    end = f"{next_year:04d}-{next_month:02d}-01"
    return name, start, end


async def ensure_partition(conn: AsyncConnection, when: datetime | None = None) -> str:
    when = when or datetime.now(UTC)
    name, start, end = _partition_bounds(when.year, when.month)
    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS cti.{name}
            PARTITION OF cti.indicator_observations
            FOR VALUES FROM ('{start}') TO ('{end}')
            """
        )
    )
    return name


async def ensure_next_n_months(conn: AsyncConnection, n: int = 3) -> list[str]:
    now = datetime.now(UTC)
    out: list[str] = []
    for i in range(n):
        year = now.year + (now.month - 1 + i) // 12
        month = (now.month - 1 + i) % 12 + 1
        name, start, end = _partition_bounds(year, month)
        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS cti.{name}
                PARTITION OF cti.indicator_observations
                FOR VALUES FROM ('{start}') TO ('{end}')
                """
            )
        )
        out.append(name)
    return out
