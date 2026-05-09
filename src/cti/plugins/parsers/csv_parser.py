"""CSV parser (sync; bridged to async)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from cti.core.errors import PermanentError
from cti.core.interfaces import SyncParser
from cti.core.models import RawPayload, RunContext


class CsvParserConfig(BaseModel):
    delimiter: str = ","
    quotechar: str = '"'
    has_header: bool = True
    skip_comment_prefix: str = "#"
    field_names: list[str] = Field(default_factory=list)
    encoding: str = "utf-8"


class CsvParser(SyncParser[CsvParserConfig]):
    name = "csv"
    config_model = CsvParserConfig

    def parse_sync(
        self, payload: RawPayload, ctx: RunContext
    ) -> Iterable[dict[str, Any]]:
        try:
            text = payload.body.decode(self.config.encoding)
        except UnicodeDecodeError as exc:
            raise PermanentError(f"csv decode error: {exc}") from exc

        lines = (
            line for line in text.splitlines() if line and not line.startswith(self.config.skip_comment_prefix)
        )
        reader = csv.reader(
            io.StringIO("\n".join(lines)),
            delimiter=self.config.delimiter,
            quotechar=self.config.quotechar,
        )
        rows = list(reader)
        if not rows:
            return []
        if self.config.has_header:
            header = [h.strip() for h in rows[0]]
            data = rows[1:]
        elif self.config.field_names:
            header = list(self.config.field_names)
            data = rows
        else:
            header = [f"col{i}" for i in range(len(rows[0]))]
            data = rows
        return [dict(zip(header, [c.strip() for c in row], strict=False)) for row in data if row]
