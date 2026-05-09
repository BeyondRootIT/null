"""Optional ASN enrichment. No-op when DB absent."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cti.core.enums import IndicatorType
from cti.core.interfaces import SyncEnricher
from cti.core.models import Indicator, RunContext


class AsnConfig(BaseModel):
    db_path: str | None = None


class AsnEnricher(SyncEnricher[AsnConfig]):
    name = "asn"
    config_model = AsnConfig

    def __init__(self, config: AsnConfig) -> None:
        super().__init__(config)
        self._reader = None
        if config.db_path and Path(config.db_path).exists():
            try:
                import maxminddb  # type: ignore[import-not-found]

                self._reader = maxminddb.open_database(config.db_path)
            except ImportError:
                self._reader = None

    def enrich_sync(self, ind: Indicator, ctx: RunContext) -> Indicator | None:
        if self._reader is None or ind.type not in (IndicatorType.IPV4, IndicatorType.IPV6):
            return ind
        try:
            record = self._reader.get(ind.value)
        except Exception:  # noqa: BLE001
            return ind
        if record and "autonomous_system_number" in record:
            tags = list(ind.tags)
            tags.append(f"asn:AS{record['autonomous_system_number']}")
            ind.tags = tuple(dict.fromkeys(tags))
        return ind
