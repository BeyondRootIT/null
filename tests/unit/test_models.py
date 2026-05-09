from __future__ import annotations

from cti.core.enums import IndicatorType, TLP
from cti.core.models import SCHEMA_VERSION, Indicator
from cti.security.tlp import tlp_max


def test_indicator_build_canonicalizes_and_derives_uuid():
    a = Indicator.build(indicator_type=IndicatorType.DOMAIN, value="Example.COM")
    b = Indicator.build(indicator_type=IndicatorType.DOMAIN, value="example.com")
    assert a.id == b.id
    assert a.value == "example.com"
    assert a.schema_version == SCHEMA_VERSION


def test_tlp_max_picks_strictest():
    assert tlp_max(TLP.GREEN, TLP.AMBER, TLP.CLEAR) == TLP.AMBER
    assert tlp_max(TLP.AMBER_STRICT, TLP.RED) == TLP.RED
