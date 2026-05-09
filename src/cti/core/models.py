"""Canonical Pydantic record types that flow through the pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cti.core.enums import IndicatorType, RunState, Severity, TLP
from cti.core.hashing import canonicalize, indicator_uuid

# Schema version stamped on every persisted record. Bump on backwards-incompatible
# changes to `Indicator` or `Observation`. Upgraders live in cti.persistence.upgraders.
SCHEMA_VERSION: str = "1"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RawPayload(BaseModel):
    """Bytes (and metadata) returned by a Connector. The Parse stage consumes these."""

    model_config = ConfigDict(frozen=True)

    body: bytes
    content_type: str = "application/octet-stream"
    headers: dict[str, str] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=_utcnow)
    etag: str | None = None
    last_modified: str | None = None
    source_url: str | None = None


class RunContext(BaseModel):
    """Per-run mutable context shared across stages.

    Carries IDs for correlation, the current watermark, and a place for stages to
    stash side-band data (e.g., raw_uri after Fetch writes to S3).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID = Field(default_factory=uuid4)
    source_id: str
    started_at: datetime = Field(default_factory=_utcnow)
    correlation_id: str = Field(default_factory=lambda: uuid4().hex)
    watermark: dict[str, Any] = Field(default_factory=dict)
    raw_uri: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class Indicator(BaseModel):
    """Canonical, deduplicated unit. UUID is derived from `(type, value)`."""

    model_config = ConfigDict(frozen=False)

    id: UUID
    type: IndicatorType
    value: str
    pattern: str | None = None
    confidence: int = Field(default=50, ge=0, le=100)
    severity: Severity = Severity.INFO
    tlp: TLP = TLP.AMBER
    tags: tuple[str, ...] = ()
    first_seen_by_us: datetime = Field(default_factory=_utcnow)
    last_seen_by_us: datetime = Field(default_factory=_utcnow)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    schema_version: str = SCHEMA_VERSION

    @field_validator("value")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @classmethod
    def build(
        cls,
        *,
        indicator_type: IndicatorType,
        value: str,
        **fields: Any,
    ) -> Indicator:
        """Construct an Indicator with canonical value and derived UUID."""
        canonical = canonicalize(indicator_type, value)
        return cls(
            id=indicator_uuid(indicator_type, canonical),
            type=indicator_type,
            value=canonical,
            **fields,
        )


class Observation(BaseModel):
    """A single sighting of an indicator by one source during one run."""

    model_config = ConfigDict(frozen=False)

    indicator_id: UUID
    source_id: str
    feed_run_id: UUID
    observed_at: datetime = Field(default_factory=_utcnow)
    tlp: TLP = TLP.AMBER
    confidence: int = Field(default=50, ge=0, le=100)
    raw: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


class RunResult(BaseModel):
    """Outcome of a single feed run; persisted to `feed_runs`."""

    run_id: UUID
    source_id: str
    state: RunState
    started_at: datetime
    finished_at: datetime
    fetched_bytes: int = 0
    records_in: int = 0
    records_out: int = 0
    parse_errors: int = 0
    dropped_by_enricher: int = 0
    dropped_by_dedup: int = 0
    error: str | None = None
    watermark: dict[str, Any] = Field(default_factory=dict)
    raw_uri: str | None = None
