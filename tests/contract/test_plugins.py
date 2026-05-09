"""Contract tests: every shipped plugin must declare a name + config_model."""

from __future__ import annotations

from pydantic import BaseModel

from cti.core.interfaces import Connector, Enricher, Parser, Publisher
from cti.plugins.loader import discover

CONTRACT = {
    "cti.connectors": Connector,
    "cti.parsers": Parser,
    "cti.enrichers": Enricher,
    "cti.publishers": Publisher,
}


def test_every_plugin_has_name_and_config_model():
    found = discover()
    for group, expected in CONTRACT.items():
        assert found[group], f"no plugins in group {group}"
        for name, cls in found[group].items():
            assert issubclass(cls, expected), f"{group}:{name} != {expected.__name__}"
            assert getattr(cls, "name", None) == name, f"{group}:{name} mismatch"
            assert issubclass(cls.config_model, BaseModel), f"{group}:{name} bad config_model"


def test_postgres_publisher_present():
    found = discover()
    assert "postgres" in found["cti.publishers"]
