"""Drops indicators that match an allowlist (RFC1918, top-domains, …)."""

from __future__ import annotations

import ipaddress

from pydantic import BaseModel, Field

from cti.core.enums import IndicatorType
from cti.core.interfaces import SyncEnricher
from cti.core.models import Indicator, RunContext

_PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]


class AllowlistConfig(BaseModel):
    drop_private_ips: bool = True
    domains: list[str] = Field(default_factory=list)
    ips: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)


class AllowlistEnricher(SyncEnricher[AllowlistConfig]):
    name = "allowlist"
    config_model = AllowlistConfig

    def enrich_sync(self, ind: Indicator, ctx: RunContext) -> Indicator | None:
        if ind.type in (IndicatorType.IPV4, IndicatorType.IPV6):
            try:
                ip = ipaddress.ip_address(ind.value)
            except ValueError:
                return ind
            if self.config.drop_private_ips and any(ip in net for net in _PRIVATE_NETS):
                return None
            if any(str(ip) == s for s in self.config.ips):
                return None
        elif ind.type == IndicatorType.DOMAIN:
            v = ind.value.lower()
            for d in self.config.domains:
                d = d.lower()
                if v == d or v.endswith("." + d):
                    return None
        elif ind.type == IndicatorType.URL:
            for u in self.config.urls:
                if ind.value.startswith(u):
                    return None
        return ind
