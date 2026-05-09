"""Typer entry point."""

from __future__ import annotations

import typer

from cti.cli.commands import dlq as dlq_cmds
from cti.cli.commands import (
    api,
    backfill,
    config_cmd,
    db,
    plugins,
    replay,
    run_once,
    scheduler,
    sources,
    worker,
)

app = typer.Typer(no_args_is_help=True, add_completion=False, help="CTI ingestion framework")

app.command("run-once")(run_once.run_once)
app.command("list-sources")(sources.list_sources)
app.command("validate-config")(sources.validate_config)
app.command("show-effective-config")(sources.show_effective_config)
app.command("plugins")(plugins.plugins)
app.command("backfill")(backfill.backfill)
app.command("replay")(replay.replay)
app.command("scheduler")(scheduler.scheduler)
app.command("worker")(worker.worker)
app.command("api")(api.api)
app.command("show-config")(config_cmd.show_config)

app.add_typer(db.app, name="db")
app.add_typer(dlq_cmds.app, name="dlq")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
