"""`cti api` — boots the read/trigger HTTP API + healthz/readyz/metrics."""

from __future__ import annotations

import typer

from cti.config.schema import get_settings
from cti.manager.registry import SourceRegistry
from cti.obs.http_app import build_app
from cti.obs.logging import configure
from cti.persistence.db import init_engine


def api(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Run the ASGI API on host:port (defaults from CTI_OBS_API_PORT)."""
    settings = get_settings()
    configure(settings.obs.log_level, settings.obs.log_json)
    init_engine(settings.db.dsn)
    registry = SourceRegistry(settings.runtime.sources_file).load()
    app = build_app(registry)
    import uvicorn

    uvicorn.run(app, host=host, port=port or settings.obs.api_port, log_config=None)
