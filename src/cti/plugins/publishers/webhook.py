"""Generic webhook publisher (POST JSON to a URL). v0 stub; production polish in v0.1."""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, Field

from cti.core.errors import TLPViolation
from cti.core.interfaces import Publisher
from cti.core.models import Indicator, Observation, RunContext


class WebhookPublisherConfig(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    bearer: str | None = None
    max_tlp: str = "GREEN"  # refuse anything stricter
    timeout_seconds: float = 10.0


_TLP_RANK = {"CLEAR": 0, "GREEN": 1, "AMBER": 2, "AMBER+STRICT": 3, "RED": 4}


class WebhookPublisher(Publisher[WebhookPublisherConfig]):
    name = "webhook"
    config_model = WebhookPublisherConfig

    def __init__(self, config: WebhookPublisherConfig) -> None:
        super().__init__(config)
        self._client = httpx.AsyncClient(timeout=config.timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def publish(
        self,
        batch: list[tuple[Indicator, Observation]],
        ctx: RunContext,
    ) -> None:
        max_allowed = _TLP_RANK[self.config.max_tlp]
        filtered = [
            (ind, obs) for ind, obs in batch if _TLP_RANK[ind.tlp.value] <= max_allowed
        ]
        if not filtered:
            raise TLPViolation("all records exceed webhook max_tlp")
        payload = [
            {
                "id": str(ind.id),
                "type": ind.type.value,
                "value": ind.value,
                "confidence": ind.confidence,
                "tlp": ind.tlp.value,
                "tags": list(ind.tags),
                "first_seen_by_us": ind.first_seen_by_us.isoformat(),
                "last_seen_by_us": ind.last_seen_by_us.isoformat(),
                "source_id": obs.source_id,
                "feed_run_id": str(obs.feed_run_id),
            }
            for ind, obs in filtered
        ]
        headers = dict(self.config.headers)
        if self.config.bearer:
            headers["Authorization"] = f"Bearer {self.config.bearer}"
        headers.setdefault("Content-Type", "application/json")
        await self._client.post(self.config.url, content=json.dumps(payload), headers=headers)
