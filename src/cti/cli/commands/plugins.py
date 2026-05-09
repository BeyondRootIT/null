"""`cti plugins` — discovered entry points by group."""

from __future__ import annotations

import typer

from cti.plugins.loader import discover


def plugins() -> None:
    """List all discovered plugins (entry-point groups)."""
    found = discover()
    for group, plugins_in_group in found.items():
        typer.echo(f"# {group}")
        if not plugins_in_group:
            typer.echo("  (none)")
            continue
        for name, cls in sorted(plugins_in_group.items()):
            typer.echo(f"  {name}\t{cls.__module__}.{cls.__name__}")
