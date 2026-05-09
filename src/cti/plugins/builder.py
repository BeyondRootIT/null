"""Builds a PipelineSpec from a SourceConfig by loading all referenced plugins."""

from __future__ import annotations

from cti.core.interfaces import Publisher
from cti.core.pipeline import PipelineSpec
from cti.manager.registry import SourceConfig
from cti.plugins.loader import (
    load_connector,
    load_enricher,
    load_parser,
    load_publisher,
)


async def build_pipeline_spec(
    source: SourceConfig, *, replay_from_uri: str | None = None
) -> PipelineSpec:
    connector = load_connector(source.plugin, source.params)
    parser = load_parser(source.parser, source.parser_params)

    enrichers = [
        load_enricher(name, source.enricher_params.get(name, {}))
        for name in source.enrichers
    ]

    pub_names = source.publishers or ["postgres"]
    if "postgres" not in pub_names:
        pub_names = ["postgres", *pub_names]

    canonical: Publisher | None = None
    extras: list[Publisher] = []
    for name in pub_names:
        instance = load_publisher(name, source.publisher_params.get(name, {}))
        if name == "postgres" and canonical is None:
            canonical = instance
        else:
            extras.append(instance)
    assert canonical is not None  # postgres is always present

    return PipelineSpec(
        connector=connector,
        parser=parser,
        enrichers=enrichers,
        canonical_publisher=canonical,
        extra_publishers=extras,
        normalize=source.normalize,
        archive=None,  # archive wired by the worker startup; injectable later
        bloom=None,
    )
