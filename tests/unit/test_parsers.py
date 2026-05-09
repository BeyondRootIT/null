from __future__ import annotations

import pytest

from cti.core.models import RawPayload, RunContext
from cti.plugins.parsers.csv_parser import CsvParser, CsvParserConfig
from cti.plugins.parsers.json_parser import JsonParser, JsonParserConfig
from cti.plugins.parsers.txt_extractor import TxtExtractor, TxtExtractorConfig


@pytest.mark.asyncio
async def test_csv_skips_comments_and_uses_headers():
    parser = CsvParser(
        CsvParserConfig(
            has_header=False,
            field_names=["a", "b"],
            skip_comment_prefix="#",
        )
    )
    payload = RawPayload(body=b"# header\n1,foo\n2,bar\n", content_type="text/csv")
    ctx = RunContext(source_id="t")
    out = [r async for r in parser.parse(payload, ctx)]
    assert out == [{"a": "1", "b": "foo"}, {"a": "2", "b": "bar"}]


@pytest.mark.asyncio
async def test_json_root_path_list():
    parser = JsonParser(JsonParserConfig(root_path="data.items"))
    payload = RawPayload(body=b'{"data":{"items":[{"v":1},{"v":2}]}}', content_type="application/json")
    ctx = RunContext(source_id="t")
    out = [r async for r in parser.parse(payload, ctx)]
    assert out == [{"v": 1}, {"v": 2}]


@pytest.mark.asyncio
async def test_txt_extracts_ipv4_skips_comments():
    parser = TxtExtractor(TxtExtractorConfig(extract=["ipv4"], skip_comment_prefix="#"))
    payload = RawPayload(body=b"# comment\n8.8.8.8\nbad-line\n1.1.1.1\n", content_type="text/plain")
    ctx = RunContext(source_id="t")
    out = [r["value"] async for r in parser.parse(payload, ctx)]
    assert out == ["8.8.8.8", "1.1.1.1"]
