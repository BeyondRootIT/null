"""Compose layered config: defaults.yaml -> sources.yaml -> env."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cti.config.secrets import resolve_secrets


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return resolve_secrets(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge with nested dict union; lists are replaced, not appended."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out
