"""Kafka publisher (stub). Wired with aiokafka in v0.1; v0 raises if used without optional dep."""

from __future__ import annotations

from pydantic import BaseModel, Field

from cti.core.errors import PluginConfigError, TLPViolation
from cti.core.interfaces import Publisher
from cti.core.models import Indicator, Observation, RunContext


class KafkaPublisherConfig(BaseModel):
    bootstrap_servers: str
    topic: str
    headers: dict[str, str] = Field(default_factory=dict)
    max_tlp: str = "GREEN"


_TLP_RANK = {"CLEAR": 0, "GREEN": 1, "AMBER": 2, "AMBER+STRICT": 3, "RED": 4}


class KafkaPublisher(Publisher[KafkaPublisherConfig]):
    name = "kafka"
    config_model = KafkaPublisherConfig

    def __init__(self, config: KafkaPublisherConfig) -> None:
        super().__init__(config)
        try:
            from aiokafka import AIOKafkaProducer  # type: ignore[import-not-found]

            self._producer_cls = AIOKafkaProducer
            self._producer: object | None = None
        except ImportError as exc:
            raise PluginConfigError(
                "kafka publisher requires the 'kafka' extra (`pip install cti[kafka]`)"
            ) from exc

    async def _ensure_producer(self) -> object:
        if self._producer is None:
            producer = self._producer_cls(bootstrap_servers=self.config.bootstrap_servers)
            await producer.start()  # type: ignore[attr-defined]
            self._producer = producer
        return self._producer

    async def aclose(self) -> None:
        if self._producer is not None:
            await self._producer.stop()  # type: ignore[attr-defined]
            self._producer = None

    async def publish(
        self,
        batch: list[tuple[Indicator, Observation]],
        ctx: RunContext,
    ) -> None:
        import json

        max_allowed = _TLP_RANK[self.config.max_tlp]
        filtered = [
            (ind, obs) for ind, obs in batch if _TLP_RANK[ind.tlp.value] <= max_allowed
        ]
        if not filtered:
            raise TLPViolation("all records exceed kafka max_tlp")
        producer = await self._ensure_producer()
        for ind, obs in filtered:
            payload = {
                "id": str(ind.id),
                "type": ind.type.value,
                "value": ind.value,
                "tlp": ind.tlp.value,
                "tags": list(ind.tags),
                "source_id": obs.source_id,
                "feed_run_id": str(obs.feed_run_id),
            }
            await producer.send_and_wait(  # type: ignore[attr-defined]
                self.config.topic, json.dumps(payload).encode()
            )
