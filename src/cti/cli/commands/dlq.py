"""`cti dlq list|show|replay`."""

from __future__ import annotations

import asyncio
import json

import typer

from cti.config.schema import get_settings
from cti.persistence.db import db_session, init_engine
from cti.persistence.models import DeadLetterRow
from cti.persistence.repositories import DeadLetterRepo

app = typer.Typer(help="Dead-letter operations")


@app.command("list")
def list_dlq(
    source: str | None = typer.Option(None, "--source"),
    show_all: bool = typer.Option(False, "--all", help="Include replayed entries"),
) -> None:
    async def _go() -> None:
        settings = get_settings()
        init_engine(settings.db.dsn)
        async with db_session() as session:
            rows = await DeadLetterRepo(session).list(source, not show_all, limit=200)
        for row in rows:
            typer.echo(
                f"{row.id}\t{row.source_id}\t{row.error_class}\t"
                f"{row.created_at.isoformat()}\t{(row.error_msg or '')[:80]}"
            )

    asyncio.run(_go())


@app.command("show")
def show(dlq_id: int) -> None:
    async def _go() -> None:
        settings = get_settings()
        init_engine(settings.db.dsn)
        async with db_session() as session:
            row = await session.get(DeadLetterRow, dlq_id)
        if row is None:
            typer.echo("not found", err=True)
            raise typer.Exit(1)
        typer.echo(
            json.dumps(
                {
                    "id": row.id,
                    "feed_run_id": str(row.feed_run_id),
                    "source_id": row.source_id,
                    "error_class": row.error_class,
                    "error_msg": row.error_msg,
                    "reason": row.reason,
                    "traceback": row.traceback,
                    "created_at": row.created_at.isoformat(),
                    "replayed_at": row.replayed_at.isoformat() if row.replayed_at else None,
                },
                indent=2,
            )
        )

    asyncio.run(_go())


@app.command("replay")
def replay(dlq_id: int) -> None:
    async def _go() -> None:
        settings = get_settings()
        init_engine(settings.db.dsn)
        async with db_session() as session:
            await DeadLetterRepo(session).mark_replayed(dlq_id)
            await session.commit()
        typer.echo(f"marked {dlq_id} replayed")

    asyncio.run(_go())
