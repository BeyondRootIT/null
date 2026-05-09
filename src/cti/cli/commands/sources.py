"""`cti list-sources`, `validate-config`, `show-effective-config`."""

from __future__ import annotations

import json

import typer

from cti.config.schema import get_settings
from cti.manager.registry import SourceRegistry


def _registry() -> SourceRegistry:
    return SourceRegistry(get_settings().runtime.sources_file).load()


def list_sources() -> None:
    """List registered sources from sources.yaml."""
    registry = _registry()
    for source in registry.all():
        typer.echo(
            f"{source.id}\t{source.plugin}\tenabled={source.enabled}\tschedule='{source.schedule}'"
        )


def validate_config() -> None:
    """Validate sources.yaml and exit non-zero on error."""
    try:
        registry = _registry()
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"OK: {len(registry.all())} sources")


def show_effective_config(source_id: str) -> None:
    """Resolve and print the effective config for one source (secrets masked)."""
    registry = _registry()
    cfg = registry.get(source_id)
    dumped = cfg.model_dump(mode="json")

    def _mask(d: object) -> object:
        if isinstance(d, dict):
            return {
                k: ("***" if k.lower() in {"auth_bearer", "bearer", "password", "token"} else _mask(v))
                for k, v in d.items()
            }
        if isinstance(d, list):
            return [_mask(x) for x in d]
        return d

    typer.echo(json.dumps(_mask(dumped), indent=2, default=str))
