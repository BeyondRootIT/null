# Tutorial 3 — Write a custom plugin

You'll ship a Connector + Parser as a separate Python package so a CTI source
the framework doesn't yet understand becomes one config-only source from then
on. ~30 minutes.

The example: a fake "ThreatJSON" feed that returns paginated JSON with a
custom envelope:

```json
{
  "next_cursor": "abc",
  "items": [
    {"observable_type": "ip", "value": "1.2.3.4", "score": 80, "tags": ["c2"]}
  ]
}
```

## Step 1 — Scaffold the package

```bash
mkdir cti-threatjson && cd cti-threatjson
mkdir -p src/cti_threatjson
touch src/cti_threatjson/__init__.py
```

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cti-threatjson"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["cti", "httpx[http2]>=0.27", "pydantic>=2.7"]

[project.entry-points."cti.connectors"]
threatjson = "cti_threatjson.connector:ThreatJsonConnector"

[project.entry-points."cti.parsers"]
threatjson = "cti_threatjson.parser:ThreatJsonParser"

[tool.hatch.build.targets.wheel]
packages = ["src/cti_threatjson"]
```

## Step 2 — Connector with cursor pagination

`src/cti_threatjson/connector.py`:

```python
from collections.abc import AsyncIterator
import httpx
from pydantic import BaseModel
from cti.core.errors import RateLimited, TransientError
from cti.core.interfaces import Connector
from cti.core.models import RawPayload, RunContext
from cti.security.egress import check_url


class ThreatJsonConnectorConfig(BaseModel):
    url: str
    auth_bearer: str | None = None
    page_size: int = 500
    timeout_seconds: float = 60.0


class ThreatJsonConnector(Connector[ThreatJsonConnectorConfig]):
    name = "threatjson"
    config_model = ThreatJsonConnectorConfig

    def __init__(self, config: ThreatJsonConnectorConfig) -> None:
        super().__init__(config)
        self._client = httpx.AsyncClient(
            http2=True, timeout=httpx.Timeout(config.timeout_seconds)
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, ctx: RunContext) -> AsyncIterator[RawPayload]:
        await check_url(self.config.url)
        cursor = ctx.watermark.get("cursor")
        headers = {}
        if self.config.auth_bearer:
            headers["Authorization"] = f"Bearer {self.config.auth_bearer}"

        while True:
            params = {"limit": self.config.page_size}
            if cursor:
                params["cursor"] = cursor
            try:
                r = await self._client.get(self.config.url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise TransientError(f"http error: {exc}") from exc

            if r.status_code == 429:
                raise RateLimited(retry_after=float(r.headers.get("Retry-After", "5")))
            if 500 <= r.status_code < 600:
                raise TransientError(f"upstream {r.status_code}")
            r.raise_for_status()

            yield RawPayload(body=r.content, content_type="application/json")

            data = r.json()
            cursor = data.get("next_cursor")
            if not cursor:
                break
        ctx.watermark["cursor"] = cursor
```

What you get for free:

- Retries on `TransientError` / `RateLimited` (exponential backoff with jitter).
- Circuit breaker per source.
- SSRF guard via `check_url()`.
- The watermark you write into `ctx.watermark` is persisted on success.

## Step 3 — Parser

`src/cti_threatjson/parser.py`:

```python
import json
from collections.abc import Iterable
from pydantic import BaseModel
from cti.core.errors import PermanentError
from cti.core.interfaces import SyncParser
from cti.core.models import RawPayload, RunContext

# Map vendor-specific types to canonical IndicatorType strings.
_TYPE_MAP = {"ip": "ipv4", "domain": "domain", "url": "url", "sha256": "sha256"}


class ThreatJsonParserConfig(BaseModel):
    pass


class ThreatJsonParser(SyncParser[ThreatJsonParserConfig]):
    name = "threatjson"
    config_model = ThreatJsonParserConfig

    def parse_sync(self, payload: RawPayload, ctx: RunContext) -> Iterable[dict]:
        try:
            doc = json.loads(payload.body)
        except json.JSONDecodeError as exc:
            raise PermanentError(f"bad json: {exc}") from exc
        for item in doc.get("items", []):
            mapped = _TYPE_MAP.get(item.get("observable_type"))
            if not mapped:
                continue
            yield {
                "type": mapped,
                "value": item["value"],
                "score": item.get("score", 50),
                "tags": item.get("tags", []),
            }
```

## Step 4 — Install and discover

```bash
cd cti-threatjson
pip install -e .
cti plugins | grep threatjson
# threatjson    cti_threatjson.connector.ThreatJsonConnector
# threatjson    cti_threatjson.parser.ThreatJsonParser
```

The framework picked up your plugins via entry points — no code changes
needed in cti itself.

## Step 5 — Wire a source

In `config/sources.yaml`:

```yaml
  - id: vendor_x
    name: "Vendor X ThreatJSON"
    plugin: threatjson
    parser: threatjson
    enrichers: [allowlist]
    schedule: "0 */1 * * *"
    rate_limit_rps: 0.5
    tlp: AMBER
    params:
      url: "https://api.vendor-x.example.com/v1/iocs"
      auth_bearer: "${env:VENDOR_X_TOKEN}"
      page_size: 1000
    parser_params: {}
    normalize:
      type_field: type
      value_field: value
      confidence_field: score
      tags_field: tags
      static_tags: ["vendor-x"]
      tlp_default: AMBER
```

```bash
export VENDOR_X_TOKEN=...
cti validate-config
cti run-once vendor_x
```

## Step 6 — Add tests

In your plugin package, mirror the framework's contract tests:

```python
# tests/test_contract.py
from pydantic import BaseModel
from cti_threatjson.connector import ThreatJsonConnector
from cti_threatjson.parser import ThreatJsonParser

def test_connector_contract():
    assert ThreatJsonConnector.name == "threatjson"
    assert issubclass(ThreatJsonConnector.config_model, BaseModel)

def test_parser_contract():
    assert ThreatJsonParser.name == "threatjson"
    assert issubclass(ThreatJsonParser.config_model, BaseModel)
```

## Tips

- **Be honest about errors.** Map upstream signals to the right error class
  (see [`technical/plugin-sdk.md`](../technical/plugin-sdk.md#error-contract)).
  A 401 is `PermanentError`; a 503 is `TransientError`. The manager makes
  retry decisions based on these classes.
- **Use the watermark.** Don't re-fetch the whole feed every cron tick. ETag,
  Last-Modified, cursor — pick what your upstream supports.
- **Don't reinvent HTTP.** If you're writing yet another HTTP/JSON connector,
  consider subclassing `HttpConnectorBase` instead of building from scratch.
- **`aclose()` matters.** The runner calls it after every run; not closing
  HTTP clients leaks file descriptors.
- **TLP is per-observation.** Returning `tlp` per-record from your normalize
  step lets multi-source consumers compute the strictest visible TLP at
  publish time.
