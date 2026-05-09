"""`cti show-config` — print current Settings (env-resolved)."""

from __future__ import annotations

import json

import typer

from cti.config.schema import get_settings


def show_config() -> None:
    """Show resolved framework settings (env vars only; secrets masked)."""
    settings = get_settings().model_dump(mode="json")

    def _mask(d: object) -> object:
        if isinstance(d, dict):
            return {
                k: ("***" if any(s in k.lower() for s in ("password", "token", "dsn")) else _mask(v))
                for k, v in d.items()
            }
        if isinstance(d, list):
            return [_mask(x) for x in d]
        return d

    typer.echo(json.dumps(_mask(settings), indent=2))
