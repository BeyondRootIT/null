"""Refangs `hxxp[://]`, `[.]`, `(.)`, `[at]` etc. Idempotent."""

from __future__ import annotations

import re

from pydantic import BaseModel

from cti.core.interfaces import SyncEnricher
from cti.core.models import Indicator, RunContext

_PATTERNS = [
    (re.compile(r"\[\.\]"), "."),
    (re.compile(r"\(\.\)"), "."),
    (re.compile(r"\{dot\}", re.IGNORECASE), "."),
    (re.compile(r"\[at\]", re.IGNORECASE), "@"),
    (re.compile(r"\[://\]", re.IGNORECASE), "://"),
    (re.compile(r"\bhxxp(s?)://", re.IGNORECASE), r"http\1://"),
    (re.compile(r"\bh\[ttp\](s?)://", re.IGNORECASE), r"http\1://"),
]


class DefangConfig(BaseModel):
    enabled: bool = True


class DefangEnricher(SyncEnricher[DefangConfig]):
    name = "defang"
    config_model = DefangConfig

    def enrich_sync(self, ind: Indicator, ctx: RunContext) -> Indicator | None:
        if not self.config.enabled:
            return ind
        value = ind.value
        for pat, repl in _PATTERNS:
            value = pat.sub(repl, value)
        if value != ind.value:
            ind.value = value
        return ind
