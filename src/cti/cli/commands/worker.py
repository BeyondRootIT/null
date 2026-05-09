"""`cti worker` — boots an arq worker."""

from __future__ import annotations

import sys

import typer


def worker() -> None:
    """Run an arq worker (uses `cti.manager.worker.WorkerSettings`)."""
    try:
        from arq import run_worker
    except ImportError as exc:
        typer.echo(f"arq not installed: {exc}", err=True)
        sys.exit(2)
    from cti.manager.worker import WorkerSettings

    run_worker(WorkerSettings)
