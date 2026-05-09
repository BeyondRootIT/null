"""Line-based regex/CIDR/domain/url/hash extractor for unstructured TXT feeds."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from cti.core.interfaces import SyncParser
from cti.core.models import RawPayload, RunContext

_RE_IPV4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?\b")
_RE_IPV6 = re.compile(r"\b[0-9a-fA-F:]{2,39}\b")
_RE_DOMAIN = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.IGNORECASE
)
_RE_URL = re.compile(r"\bhttps?://[^\s\"'<>]+", re.IGNORECASE)
_RE_HASH = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")


class TxtExtractorConfig(BaseModel):
    extract: list[str] = Field(default_factory=lambda: ["ipv4"])
    skip_comment_prefix: str = "#"
    expand_cidrs: bool = False
    encoding: str = "utf-8"


def _extract_ipv4(line: str, expand_cidrs: bool) -> list[str]:
    out: list[str] = []
    for m in _RE_IPV4.finditer(line):
        token = m.group(0)
        try:
            if "/" in token:
                net = ipaddress.IPv4Network(token, strict=False)
                if expand_cidrs and net.prefixlen >= 24:
                    out.extend(str(h) for h in net.hosts())
                else:
                    out.append(str(net))
            else:
                out.append(str(ipaddress.IPv4Address(token)))
        except ValueError:
            continue
    return out


class TxtExtractor(SyncParser[TxtExtractorConfig]):
    name = "txt"
    config_model = TxtExtractorConfig

    def parse_sync(
        self, payload: RawPayload, ctx: RunContext
    ) -> Iterable[dict[str, Any]]:
        text = payload.body.decode(self.config.encoding, errors="replace")
        results: list[dict[str, Any]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(self.config.skip_comment_prefix):
                continue
            for kind in self.config.extract:
                if kind == "ipv4":
                    for v in _extract_ipv4(line, self.config.expand_cidrs):
                        results.append({"type": "ipv4", "value": v, "_raw": line})
                elif kind == "url":
                    for m in _RE_URL.findall(line):
                        results.append({"type": "url", "value": m, "_raw": line})
                elif kind == "domain":
                    for m in _RE_DOMAIN.findall(line):
                        results.append({"type": "domain", "value": m, "_raw": line})
                elif kind == "hash":
                    for m in _RE_HASH.findall(line):
                        ind_type = {32: "md5", 40: "sha1", 64: "sha256"}[len(m)]
                        results.append({"type": ind_type, "value": m, "_raw": line})
        return results
