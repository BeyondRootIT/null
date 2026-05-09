# Plugin SDK

The framework exposes **four** extension points. Plugins are discovered via
Python entry points — they're real Python packages, version-pinned and
importable, not file-drops.

| ABC | Entry-point group | Purpose |
| --- | --- | --- |
| `Connector` | `cti.connectors` | Pull raw bytes from somewhere. |
| `Parser` | `cti.parsers` | Turn bytes into untyped record dicts. |
| `Enricher` | `cti.enrichers` | Pure transform `Indicator -> Indicator?`. |
| `Publisher` | `cti.publishers` | Sink for `(Indicator, Observation)` batches. |

Defined in `src/cti/core/interfaces.py`.

## The 80% case: sync code

Most plugins are sync. The framework wraps you in `asyncio.to_thread` so
parsing, regex, and other CPU-bound work doesn't block the event loop.

### A sync parser

```python
from collections.abc import Iterable
from pydantic import BaseModel
from cti.core.interfaces import SyncParser
from cti.core.models import RawPayload, RunContext


class MyParserConfig(BaseModel):
    encoding: str = "utf-8"


class MyParser(SyncParser[MyParserConfig]):
    name = "my_parser"
    config_model = MyParserConfig

    def parse_sync(self, payload: RawPayload, ctx: RunContext) -> Iterable[dict]:
        text = payload.body.decode(self.config.encoding)
        for line in text.splitlines():
            if line and not line.startswith("#"):
                yield {"raw": line}
```

Register it in your package's `pyproject.toml`:

```toml
[project.entry-points."cti.parsers"]
my_parser = "my_pkg.parsers:MyParser"
```

Re-install (`pip install -e .`) and `cti plugins` will list it.

### A sync enricher

```python
from cti.core.interfaces import SyncEnricher
from cti.core.models import Indicator, RunContext


class TagInjectorConfig(BaseModel):
    tag: str = "from-feed-x"


class TagInjector(SyncEnricher[TagInjectorConfig]):
    name = "tag_injector"
    config_model = TagInjectorConfig

    def enrich_sync(self, ind: Indicator, ctx: RunContext) -> Indicator | None:
        ind.tags = (*ind.tags, self.config.tag)
        return ind  # returning None drops the indicator
```

## The async case

Native async is required for paginated REST, SSE, websockets, async drivers.

### An async connector

```python
from collections.abc import AsyncIterator
import httpx
from cti.core.interfaces import Connector
from cti.core.models import RawPayload, RunContext
from cti.security.egress import check_url


class MyApiConnectorConfig(BaseModel):
    url: str
    page_size: int = 100


class MyApiConnector(Connector[MyApiConnectorConfig]):
    name = "my_api"
    config_model = MyApiConnectorConfig

    def __init__(self, config):
        super().__init__(config)
        self._client = httpx.AsyncClient(http2=True)

    async def aclose(self):
        await self._client.aclose()

    async def fetch(self, ctx: RunContext) -> AsyncIterator[RawPayload]:
        await check_url(self.config.url)
        cursor = ctx.watermark.get("cursor")
        while True:
            params = {"limit": self.config.page_size}
            if cursor:
                params["cursor"] = cursor
            r = await self._client.get(self.config.url, params=params)
            r.raise_for_status()
            yield RawPayload(body=r.content, content_type="application/json")
            cursor = r.headers.get("X-Next-Cursor")
            if not cursor:
                break
        ctx.watermark["cursor"] = cursor
```

### An async publisher

```python
class MySinkPublisherConfig(BaseModel):
    bootstrap_servers: str


class MySinkPublisher(Publisher[MySinkPublisherConfig]):
    name = "my_sink"
    config_model = MySinkPublisherConfig

    async def publish(self, batch, ctx) -> None:
        for ind, obs in batch:
            ...
```

## Error contract

Plugins **must** raise the right error class so the manager can decide
correctly. Defined in `cti/core/errors.py`.

| Raise | When | Manager does |
| --- | --- | --- |
| `TransientError` | Network blip, 5xx, connection reset | Retries with exponential backoff. |
| `RateLimited(retry_after=…)` | 429 | Retries; honours `retry_after`. |
| `PermanentError` | 4xx (auth, not-found), parse failure, contract violation | Records to `dead_letters`; no retry. |
| `EgressBlocked` | SSRF guard rejected URL | `PermanentError` subclass. |
| `TLPViolation` | Publisher cannot accept this TLP | Indicator dropped for that publisher only. |

Raising bare `Exception` is treated as a transient failure but logged loudly.
Don't do it.

## Configuration

Each plugin declares a Pydantic `config_model`. Source YAML feeds it via
`params` / `parser_params` / `enricher_params[name]` / `publisher_params[name]`
(see [`configuration.md`](../user-guide/configuration.md)). Validation runs at
startup, so misconfig fails fast.

## Conventions

- **`name`** must equal the entry-point name (asserted by the contract test).
- **`config_model`** must be a Pydantic `BaseModel`.
- **`aclose()`** override if you hold resources (HTTP clients, file handles, sockets).
- **`metrics()`** returning `[(suffix, help)]` lets you declare custom metrics;
  the framework prefixes them `cti_plugin_<name>_*` to avoid registry collisions.
- Treat `RunContext` as **shared mutable state** for the run only — not for
  cross-run persistence. Use the watermark on `feed_runs` for that.
