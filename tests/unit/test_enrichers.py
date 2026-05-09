from __future__ import annotations

import pytest

from cti.core.enums import IndicatorType
from cti.core.models import Indicator, RunContext
from cti.plugins.enrichers.allowlist import AllowlistConfig, AllowlistEnricher
from cti.plugins.enrichers.defang import DefangConfig, DefangEnricher


@pytest.mark.asyncio
async def test_defang_refangs_common_patterns():
    enricher = DefangEnricher(DefangConfig())
    ind = Indicator.build(indicator_type=IndicatorType.URL, value="hxxp://evil[.]com/foo")
    out = await enricher.enrich(ind, RunContext(source_id="t"))
    assert out is not None and "http://" in out.value and "evil.com" in out.value


@pytest.mark.asyncio
async def test_allowlist_drops_private_ip():
    enricher = AllowlistEnricher(AllowlistConfig(drop_private_ips=True))
    ind = Indicator.build(indicator_type=IndicatorType.IPV4, value="192.168.0.1")
    assert await enricher.enrich(ind, RunContext(source_id="t")) is None


@pytest.mark.asyncio
async def test_allowlist_keeps_public_ip():
    enricher = AllowlistEnricher(AllowlistConfig(drop_private_ips=True))
    ind = Indicator.build(indicator_type=IndicatorType.IPV4, value="8.8.8.8")
    assert (await enricher.enrich(ind, RunContext(source_id="t"))) is ind
