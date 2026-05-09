"""Entry-point discovery for plugins."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from pydantic import BaseModel

from cti.core.errors import PluginLoadError
from cti.core.interfaces import Connector, Enricher, Parser, Plugin, Publisher

GROUP_CONNECTORS = "cti.connectors"
GROUP_PARSERS = "cti.parsers"
GROUP_ENRICHERS = "cti.enrichers"
GROUP_PUBLISHERS = "cti.publishers"

_ALL_GROUPS = (GROUP_CONNECTORS, GROUP_PARSERS, GROUP_ENRICHERS, GROUP_PUBLISHERS)


def discover() -> dict[str, dict[str, type[Plugin]]]:
    """Return `{group: {name: class}}` for all discovered entry points."""
    out: dict[str, dict[str, type[Plugin]]] = {g: {} for g in _ALL_GROUPS}
    for group in _ALL_GROUPS:
        for ep in entry_points(group=group):
            try:
                out[group][ep.name] = ep.load()
            except Exception as exc:  # noqa: BLE001
                raise PluginLoadError(
                    f"failed to load entry point {group}:{ep.name}: {exc}"
                ) from exc
    return out


def load(group: str, name: str) -> type[Plugin]:
    eps = entry_points(group=group, name=name)
    if not eps:
        raise PluginLoadError(f"no plugin {name!r} in group {group!r}")
    ep = next(iter(eps))
    try:
        return ep.load()
    except Exception as exc:
        raise PluginLoadError(f"failed to load {group}:{name}: {exc}") from exc


def instantiate(
    group: str, name: str, params: dict[str, Any]
) -> Plugin:
    cls = load(group, name)
    cfg_model: type[BaseModel] = cls.config_model
    cfg = cfg_model.model_validate(params)
    return cls(cfg)


def load_connector(name: str, params: dict[str, Any]) -> Connector:
    return instantiate(GROUP_CONNECTORS, name, params)  # type: ignore[return-value]


def load_parser(name: str, params: dict[str, Any]) -> Parser:
    return instantiate(GROUP_PARSERS, name, params)  # type: ignore[return-value]


def load_enricher(name: str, params: dict[str, Any]) -> Enricher:
    return instantiate(GROUP_ENRICHERS, name, params)  # type: ignore[return-value]


def load_publisher(name: str, params: dict[str, Any]) -> Publisher:
    return instantiate(GROUP_PUBLISHERS, name, params)  # type: ignore[return-value]
