from __future__ import annotations

import pytest

from cti.core.enums import IndicatorType
from cti.core.models import RunContext
from cti.core.queue import StageQueue
from cti.core.stages.normalize import NormalizeConfig, run_normalize


@pytest.mark.asyncio
async def test_normalize_static_type_field_map():
    cfg = NormalizeConfig(indicator_type=IndicatorType.IPV4, value_field="ip")
    inq: StageQueue[dict] = StageQueue("in")
    out: StageQueue[tuple] = StageQueue("out")
    await inq.put({"ip": "8.8.8.8"})
    await inq.put({"ip": "256.0.0.0"})
    await inq.put({"ip": "1.1.1.1"})
    await inq.close()

    await run_normalize(cfg, RunContext(source_id="t"), inq, out)

    results = []
    async for ind, _raw in out:
        results.append(ind.value)
    assert results == ["8.8.8.8", "1.1.1.1"]


@pytest.mark.asyncio
async def test_normalize_per_record_type_field():
    cfg = NormalizeConfig(type_field="t", value_field="v")
    inq: StageQueue[dict] = StageQueue("in")
    out: StageQueue[tuple] = StageQueue("out")
    await inq.put({"t": "ipv4", "v": "1.1.1.1"})
    await inq.put({"t": "domain", "v": "example.com"})
    await inq.close()

    await run_normalize(cfg, RunContext(source_id="t"), inq, out)

    types = []
    async for ind, _raw in out:
        types.append(ind.type.value)
    assert types == ["ipv4", "domain"]
