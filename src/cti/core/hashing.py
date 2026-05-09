"""Canonicalization + deterministic UUID derivation for indicator dedup."""

from __future__ import annotations

import ipaddress
import re
from uuid import UUID, uuid5

from cti.core.enums import IndicatorType

# Stable namespace; never change this value or all indicator IDs shift.
_CTI_NS = UUID("4f0c6c4a-2c8f-5f8e-9b3e-9c0a2c8f5f8e")

_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)

# Common CTI defang patterns. Applied transparently inside canonicalize so that
# feeds shipping defanged values (urlhaus does not, but most others do) survive.
_DEFANG_REPLACEMENTS = (
    ("[.]", "."),
    ("(.)", "."),
    ("[:]", ":"),
    ("[at]", "@"),
    ("[://]", "://"),
)
_RE_HXXP = re.compile(r"\bhxxp(s?)://", re.IGNORECASE)


def _refang(value: str) -> str:
    out = value
    for src, dst in _DEFANG_REPLACEMENTS:
        out = out.replace(src, dst)
    out = _RE_HXXP.sub(r"http\1://", out)
    return out


def canonicalize(indicator_type: IndicatorType, value: str) -> str:
    """Return a stable canonical form for `(type, value)`.

    Raises:
        ValueError: when value cannot be canonicalized into the declared type.
    """
    raw = value.strip()
    if not raw:
        raise ValueError("empty indicator value")

    if indicator_type == IndicatorType.IPV4:
        return str(ipaddress.IPv4Address(raw))
    if indicator_type == IndicatorType.IPV6:
        return str(ipaddress.IPv6Address(raw))
    if indicator_type == IndicatorType.DOMAIN:
        return _canonical_domain(raw)
    if indicator_type == IndicatorType.URL:
        return _canonical_url(raw)
    if indicator_type in (IndicatorType.SHA256, IndicatorType.SHA1, IndicatorType.MD5):
        return _canonical_hash(indicator_type, raw)
    if indicator_type == IndicatorType.EMAIL:
        return _canonical_email(raw)
    return raw.lower()


def _canonical_domain(value: str) -> str:
    domain = _refang(value).lower().rstrip(".")
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"invalid IDN domain: {value}") from exc
    for label in domain.split("."):
        if not _DOMAIN_LABEL_RE.match(label):
            raise ValueError(f"invalid domain label: {label}")
    return domain


def _canonical_url(value: str) -> str:
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(_refang(value).strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid URL: {value}")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if (scheme == "http" and netloc.endswith(":80")) or (
        scheme == "https" and netloc.endswith(":443")
    ):
        netloc = netloc.rsplit(":", 1)[0]
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _canonical_hash(indicator_type: IndicatorType, value: str) -> str:
    expected = {IndicatorType.MD5: 32, IndicatorType.SHA1: 40, IndicatorType.SHA256: 64}[
        indicator_type
    ]
    cleaned = value.strip().lower()
    if len(cleaned) != expected or not all(c in "0123456789abcdef" for c in cleaned):
        raise ValueError(f"invalid {indicator_type.value} hash: {value!r}")
    return cleaned


def _canonical_email(value: str) -> str:
    if "@" not in value:
        raise ValueError(f"invalid email: {value}")
    local, _, domain = value.rpartition("@")
    return f"{local}@{_canonical_domain(domain)}".lower()


def indicator_uuid(indicator_type: IndicatorType, value: str) -> UUID:
    """Deterministic UUIDv5 of (type, canonical_value). Authoritative dedup key."""
    canonical = canonicalize(indicator_type, value)
    return uuid5(_CTI_NS, f"{indicator_type.value}:{canonical}")
