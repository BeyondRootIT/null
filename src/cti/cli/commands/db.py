"""`cti db ...` — alembic helpers + partition maintenance."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import typer

from cti.config.schema import get_settings
from cti.persistence.db import get_engine, init_engine
from cti.persistence.partitioning import ensure_next_n_months

app = typer.Typer(help="Database operations")


@app.command("migrate")
def migrate() -> None:
    """Run alembic upgrade head."""
    settings = get_settings()
    env = {"CTI_DB_DSN": settings.db.dsn, "PATH": "/usr/local/bin:/usr/bin:/bin"}
    cwd = Path(__file__).resolve().parents[3]
    code = subprocess.call(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, cwd=cwd
    )
    raise typer.Exit(code)


@app.command("ensure-partitions")
def ensure_partitions(months: int = 3) -> None:
    """Create missing observation partitions for the next N months."""

    async def _go() -> None:
        settings = get_settings()
        init_engine(settings.db.dsn)
        engine = get_engine()
        async with engine.begin() as conn:
            created = await ensure_next_n_months(conn, months)
        typer.echo("\n".join(created))

    asyncio.run(_go())
