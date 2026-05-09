"""SSRF egress guard.

Refuses URLs that resolve to private, loopback, link-local, or metadata IPs
unless explicitly allowed.
"""

from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlparse

from cti.core.errors import EgressBlocked

_DENY_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",  # link-local + AWS metadata
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
]


def _is_blocked(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in _DENY_NETS)


async def check_url(url: str, *, allow_http: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EgressBlocked(f"unsupported scheme: {parsed.scheme}")
    if parsed.scheme == "http" and not allow_http:
        raise EgressBlocked(f"plaintext HTTP forbidden by default: {url}")
    host = parsed.hostname
    if not host:
        raise EgressBlocked(f"missing host in URL: {url}")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except OSError as exc:
        raise EgressBlocked(f"DNS failure for {host}: {exc}") from exc
    for info in infos:
        addr = info[4][0]
        if _is_blocked(addr):
            raise EgressBlocked(f"blocked egress: {host} -> {addr}")
