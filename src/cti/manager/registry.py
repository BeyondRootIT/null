"""SourceRegistry — load + validate `sources.yaml`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from cti.core.enums import TLP, Severity
from cti.core.stages.normalize import NormalizeConfig


class RetryPolicy(BaseModel):
    max_attempts: int = 5
    initial_seconds: float = 1.0
    max_seconds: float = 60.0
    jitter_seconds: float = 1.0


class CircuitPolicy(BaseModel):
    failure_threshold: int = 5
    recovery_seconds: float = 300.0


class SourceConfig(BaseModel):
    """Configuration for one ingestion source. Validated on startup."""

    id: str
    name: str | None = None
    plugin: str  # connector entry-point name
    enabled: bool = True
    schedule: str = "0 */6 * * *"  # cron
    jitter_seconds: int = 60
    rate_limit_rps: float | None = None
    max_parallelism: int = 1
    timeout_seconds: int = 60
    retry: RetryPolicy = RetryPolicy()
    circuit: CircuitPolicy = CircuitPolicy()
    parser: str
    enrichers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=lambda: ["postgres"])
    params: dict[str, Any] = Field(default_factory=dict)
    parser_params: dict[str, Any] = Field(default_factory=dict)
    enricher_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    publisher_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    normalize: NormalizeConfig = Field(default_factory=NormalizeConfig)
    tlp: TLP = TLP.AMBER
    severity_default: Severity = Severity.INFO
    confidence_default: int = 50
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"source id must be alnum/_/- only: {v!r}")
        return v


class SourcesFile(BaseModel):
    sources: list[SourceConfig]


class SourceRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._sources: dict[str, SourceConfig] = {}

    def load(self) -> SourceRegistry:
        from cti.config.secrets import resolve_secrets

        text = self.path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
        resolved = resolve_secrets(raw)
        parsed = SourcesFile.model_validate(resolved)
        seen: set[str] = set()
        for source in parsed.sources:
            if source.id in seen:
                raise ValueError(f"duplicate source id: {source.id}")
            seen.add(source.id)
            self._sources[source.id] = source
        return self

    def all(self) -> list[SourceConfig]:
        return list(self._sources.values())

    def get(self, source_id: str) -> SourceConfig:
        if source_id not in self._sources:
            raise KeyError(f"unknown source: {source_id}")
        return self._sources[source_id]

    def enabled(self) -> list[SourceConfig]:
        return [s for s in self._sources.values() if s.enabled]
