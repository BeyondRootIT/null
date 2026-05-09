from __future__ import annotations

import pytest

from cti.core.enums import IndicatorType
from cti.core.hashing import canonicalize, indicator_uuid


def test_ipv4_canonical():
    assert canonicalize(IndicatorType.IPV4, " 8.8.8.8 ") == "8.8.8.8"


def test_ipv6_canonical():
    assert canonicalize(IndicatorType.IPV6, "2001:DB8::1") == "2001:db8::1"


def test_domain_canonical():
    assert canonicalize(IndicatorType.DOMAIN, "Example.COM.") == "example.com"


def test_url_canonical_strips_default_port_and_fragment():
    canonical = canonicalize(IndicatorType.URL, "HTTP://Example.com:80/Foo?a=1#frag")
    assert canonical == "http://example.com/Foo?a=1"


def test_hash_canonical():
    h = "AABBCCDDEEFF11223344556677889900AABBCCDDEEFF11223344556677889900"
    assert canonicalize(IndicatorType.SHA256, h) == h.lower()


@pytest.mark.parametrize(
    "ind_type,bad",
    [
        (IndicatorType.IPV4, "256.1.1.1"),
        (IndicatorType.SHA256, "deadbeef"),
        (IndicatorType.URL, "/relative"),
    ],
)
def test_invalid_value_raises(ind_type: IndicatorType, bad: str):
    with pytest.raises(ValueError):
        canonicalize(ind_type, bad)


def test_uuid_is_deterministic_and_value_independent_of_case():
    a = indicator_uuid(IndicatorType.DOMAIN, "Example.COM")
    b = indicator_uuid(IndicatorType.DOMAIN, "example.com")
    assert a == b
