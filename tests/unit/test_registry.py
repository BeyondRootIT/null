from __future__ import annotations

from pathlib import Path

import pytest

from cti.manager.registry import SourceRegistry

EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "sources.example.yaml"


def test_loads_example_sources():
    registry = SourceRegistry(EXAMPLE).load()
    ids = {s.id for s in registry.all()}
    assert "abuse_ch_urlhaus" in ids
    assert "abuse_ch_feodo_tracker" in ids


def test_get_unknown_raises():
    registry = SourceRegistry(EXAMPLE).load()
    with pytest.raises(KeyError):
        registry.get("nope")
