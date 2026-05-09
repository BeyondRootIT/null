"""Static bearer token auth with scopes loaded from a YAML file.

Format:
    tokens:
      - token: "abc123..."
        name: "operator-1"
        scopes: ["read", "trigger"]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

VALID_SCOPES: Final = {"read", "trigger", "admin"}


@dataclass(frozen=True)
class Principal:
    name: str
    scopes: frozenset[str]

    def has(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.scopes


class TokenStore:
    def __init__(self, tokens: dict[str, Principal]) -> None:
        self._tokens = tokens

    @classmethod
    def load(cls, path: str | Path | None) -> TokenStore:
        if not path or not Path(path).exists():
            return cls({})
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        out: dict[str, Principal] = {}
        for entry in raw.get("tokens", []):
            scopes = frozenset(s for s in entry.get("scopes", []) if s in VALID_SCOPES)
            out[entry["token"]] = Principal(name=entry.get("name", "anonymous"), scopes=scopes)
        return cls(out)

    def authenticate(self, header: str | None) -> Principal | None:
        if not header or not header.lower().startswith("bearer "):
            return None
        return self._tokens.get(header[7:].strip())
