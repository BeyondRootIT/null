"""Optional GeoIP enrichment via MaxMind mmdb. No-op when DB not present."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from cti.core.enums import IndicatorType
from cti.core.interfaces import SyncEnricher
from cti.core.models import Indicator, RunContext


class GeoIpConfig(BaseModel):
    db_path: str | None = None


class GeoIpEnricher(SyncEnricher[GeoIpConfig]):
    name = "geoip"
    config_model = GeoIpConfig

    def __init__(self, config: GeoIpConfig) -> None:
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
        if record:
            country = (record.get("country") or {}).get("iso_code")
            if country:
                tags = list(ind.tags)
                tags.append(f"country:{country}")
                ind.tags = tuple(dict.fromkeys(tags))
        return ind
