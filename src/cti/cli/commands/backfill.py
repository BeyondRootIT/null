"""`cti backfill --since <ISO>` — temporarily clear watermarks and run-once.

v0 stub: enqueues a normal run-once for the source after wiping the watermark.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import typer

from cti.cli.commands.run_once import run_once as _run_once
from cti.config.schema import get_settings
from cti.persistence.db import db_session, init_engine
from cti.persistence.models import SourceRow


def backfill(
    source_id: str,
    since: str = typer.Option(..., "--since", help="ISO8601 timestamp"),
) -> None:
    """Clear the source's watermark and run-once (so the next fetch is a full pull)."""
    try:
        datetime.fromisoformat(since)
    except ValueError as exc:
        typer.echo(f"invalid --since: {exc}", err=True)
        raise typer.Exit(2)

    async def _wipe() -> None:
        settings = get_settings()
        init_engine(settings.db.dsn)
        async with db_session() as session:
            row = await session.get(SourceRow, source_id)
            if row is not None:
                row.watermark = {}
                row.last_etag = None
                row.last_modified = None
                row.last_seen_id = None
                await session.commit()

    asyncio.run(_wipe())
    _run_once(source_id)
