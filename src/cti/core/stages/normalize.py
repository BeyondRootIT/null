"""Normalize stage: record dicts -> Indicator candidates.

Config-driven: a `field_map` on the source config specifies which dict key holds
the value, optionally overridden per-record by an explicit `type` field.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from cti.core.enums import IndicatorType, Severity, TLP
from cti.core.errors import PermanentError
from cti.core.models import Indicator, RunContext
from cti.core.queue import StageQueue
from cti.obs.metrics import PARSE_ERRORS


class NormalizeConfig(BaseModel):
    indicator_type: IndicatorType | None = None
    type_field: str | None = None
    value_field: str = "value"
    confidence_default: int = 50
    confidence_field: str | None = None
    severity_default: Severity = Severity.INFO
    tlp_default: TLP = TLP.AMBER
    static_tags: tuple[str, ...] = ()
    tags_field: str | None = None
    valid_from_field: str | None = None
    valid_until_field: str | None = None
    skip_on_error: bool = True
    extra_field_map: dict[str, str] = Field(default_factory=dict)


def _coerce_type(raw: str) -> IndicatorType:
    try:
        return IndicatorType(raw.lower())
    except ValueError as exc:
        raise PermanentError(f"unknown indicator type: {raw!r}") from exc


def _record_to_indicator(record: dict[str, Any], cfg: NormalizeConfig) -> Indicator | None:
    if cfg.type_field is not None:
        type_raw = record.get(cfg.type_field)
        if not type_raw:
            return None
        ind_type = _coerce_type(str(type_raw))
    elif cfg.indicator_type is not None:
        ind_type = cfg.indicator_type
    else:
        raise PermanentError("normalize: indicator_type or type_field must be set")

    value = record.get(cfg.value_field)
    if value is None or value == "":
        return None

    confidence = cfg.confidence_default
    if cfg.confidence_field and cfg.confidence_field in record:
        try:
            confidence = int(record[cfg.confidence_field])
        except (TypeError, ValueError):
            pass

    tags: list[str] = list(cfg.static_tags)
    if cfg.tags_field and cfg.tags_field in record:
        raw_tags = record[cfg.tags_field]
        if isinstance(raw_tags, list):
            tags.extend(str(t) for t in raw_tags)
        elif isinstance(raw_tags, str):
            tags.extend(t.strip() for t in raw_tags.split(",") if t.strip())

    return Indicator.build(
        indicator_type=ind_type,
        value=str(value),
        confidence=confidence,
        severity=cfg.severity_default,
        tlp=cfg.tlp_default,
        tags=tuple(dict.fromkeys(tags)),
    )


async def run_normalize(
    cfg: NormalizeConfig,
    ctx: RunContext,
    inq: StageQueue[dict[str, Any]],
    out: StageQueue[tuple[Indicator, dict[str, Any]]],
) -> None:
    try:
        async for record in inq:
            try:
                ind = _record_to_indicator(record, cfg)
            except (ValueError, PermanentError):
                PARSE_ERRORS.labels(source=ctx.source_id).inc()
                if cfg.skip_on_error:
                    continue
                raise
            if ind is None:
                continue
            await out.put((ind, record))
    finally:
        await out.close()
