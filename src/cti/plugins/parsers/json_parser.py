"""JSON / NDJSON parser with optional dotted-path root selector."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from cti.core.errors import PermanentError
from cti.core.interfaces import SyncParser
from cti.core.models import RawPayload, RunContext


class JsonParserConfig(BaseModel):
    ndjson: bool = False
    root_path: str | None = None  # dotted path; "" → whole document
    encoding: str = "utf-8"


def _resolve_path(doc: Any, path: str | None) -> Any:
    if not path:
        return doc
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


class JsonParser(SyncParser[JsonParserConfig]):
    name = "json"
    config_model = JsonParserConfig

    def parse_sync(
        self, payload: RawPayload, ctx: RunContext
    ) -> Iterable[dict[str, Any]]:
        try:
            text = payload.body.decode(self.config.encoding)
        except UnicodeDecodeError as exc:
            raise PermanentError(f"json decode error: {exc}") from exc

        if self.config.ndjson:
            out: list[dict[str, Any]] = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
            return out

        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PermanentError(f"invalid json: {exc}") from exc

        node = _resolve_path(doc, self.config.root_path)
        if isinstance(node, list):
            return [item for item in node if isinstance(item, dict)]
        if isinstance(node, dict):
            return [node]
        return []
