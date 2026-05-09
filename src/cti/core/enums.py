from __future__ import annotations

from enum import StrEnum


class IndicatorType(StrEnum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    DOMAIN = "domain"
    URL = "url"
    SHA256 = "sha256"
    SHA1 = "sha1"
    MD5 = "md5"
    EMAIL = "email"
    FILE_NAME = "file_name"
    MUTEX = "mutex"
    REGISTRY_KEY = "registry_key"
    YARA_RULE = "yara_rule"


class TLP(StrEnum):
    """TLP v2.0 — strictness ordered low → high in `_ORDER`."""

    CLEAR = "CLEAR"
    GREEN = "GREEN"
    AMBER = "AMBER"
    AMBER_STRICT = "AMBER+STRICT"
    RED = "RED"


_TLP_ORDER: dict[TLP, int] = {
    TLP.CLEAR: 0,
    TLP.GREEN: 1,
    TLP.AMBER: 2,
    TLP.AMBER_STRICT: 3,
    TLP.RED: 4,
}


def tlp_max(*values: TLP) -> TLP:
    """Return the strictest TLP among the inputs."""
    return max(values, key=lambda t: _TLP_ORDER[t])


class RunState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StageName(StrEnum):
    FETCH = "fetch"
    PARSE = "parse"
    NORMALIZE = "normalize"
    ENRICH = "enrich"
    DEDUP = "dedup"
    PERSIST = "persist"
    PUBLISH = "publish"
