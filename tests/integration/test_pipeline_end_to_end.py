"""End-to-end pipeline test against a real Postgres via testcontainers.

Requires Docker. Marked `integration` — run with `pytest -m integration`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from cti.core.enums import IndicatorType
from cti.core.interfaces import Connector
from cti.core.models import RawPayload, RunContext
from cti.core.pipeline import PipelineSpec, run_with_outcome
from cti.core.stages.normalize import NormalizeConfig
from cti.persistence.db import dispose, get_engine, init_engine
from cti.persistence.models import Base, IndicatorRow
from cti.plugins.parsers.csv_parser import CsvParser, CsvParserConfig
from cti.plugins.publishers.postgres import PostgresPublisher, PostgresPublisherConfig

pytestmark = pytest.mark.integration


class _FakeConfig(BaseModel):
    pass


class FakeConnector(Connector[_FakeConfig]):
    name = "fake"
    config_model = _FakeConfig

    async def fetch(self, ctx: RunContext) -> AsyncIterator[RawPayload]:
        yield RawPayload(body=b"value\n8.8.8.8\n1.1.1.1\n", content_type="text/csv")


@pytest.fixture(scope="module")
def pg_url() -> str:
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")


@pytest.mark.asyncio
async def test_csv_to_postgres_end_to_end(pg_url: str, tmp_path):
    init_engine(pg_url)
    async with get_engine().begin() as conn:
        await conn.run_sync(lambda c: c.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS cti"))
        await conn.run_sync(Base.metadata.create_all)

    spec = PipelineSpec(
        connector=FakeConnector(_FakeConfig()),
        parser=CsvParser(CsvParserConfig(has_header=True)),
        enrichers=[],
        canonical_publisher=PostgresPublisher(PostgresPublisherConfig()),
        normalize=NormalizeConfig(indicator_type=IndicatorType.IPV4, value_field="value"),
    )
    ctx = RunContext(source_id="t-int")
    result = await run_with_outcome(spec, ctx)
    assert result.state.value == "SUCCESS"

    async with get_engine().connect() as conn:
        rows = (await conn.execute(IndicatorRow.__table__.select())).fetchall()
    values = {r.value for r in rows}
    assert {"8.8.8.8", "1.1.1.1"}.issubset(values)
    await dispose()
