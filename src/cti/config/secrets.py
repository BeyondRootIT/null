"""Resolve `${env:VAR}` and `${file:/path}` references inside loaded YAML.

Refuses inline secrets (warnings). Recurses into dicts/lists.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_REF_RE = re.compile(r"\$\{(env|file):([^}]+)\}")


def _resolve_str(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        kind, target = m.group(1), m.group(2)
        if kind == "env":
            return os.environ.get(target, "")
        if kind == "file":
            path = Path(target)
            if not path.is_file():
                return ""
            return path.read_text(encoding="utf-8").strip()
        return m.group(0)

    return _REF_RE.sub(repl, value)


def resolve_secrets(value: Any) -> Any:
    if isinstance(value, str):
        return _resolve_str(value)
    if isinstance(value, dict):
        return {k: resolve_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_secrets(v) for v in value]
    return value
