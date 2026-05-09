"""Shared HTTP connector base. Conditional GET, decompression, SSRF guard, retries."""

from __future__ import annotations

import gzip
import io
import zipfile
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel, Field

from cti.core.errors import PermanentError, RateLimited, TransientError
from cti.core.interfaces import Connector
from cti.core.models import RawPayload, RunContext
from cti.security.egress import check_url

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MAX_BYTES = 256 * 1024 * 1024  # 256 MiB cap per fetch


class HttpConnectorConfig(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    auth_bearer: str | None = None
    auth_basic: tuple[str, str] | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_S
    max_bytes: int = DEFAULT_MAX_BYTES
    decompress: str | None = None  # "gzip" | "zip" | None
    zip_member: str | None = None
    allow_http: bool = False
    verify_ssl: bool = True
    follow_redirects: bool = True


class HttpConnectorBase(Connector[HttpConnectorConfig]):
    """Base for HTTP connectors. Handles fetch lifecycle; subclasses pick content_type."""

    config_model = HttpConnectorConfig
    default_content_type: str = "application/octet-stream"

    def __init__(self, config: HttpConnectorConfig) -> None:
        super().__init__(config)
        self._client = httpx.AsyncClient(
            http2=True,
            verify=config.verify_ssl,
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=config.follow_redirects,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, ctx: RunContext) -> AsyncIterator[RawPayload]:  # type: ignore[override]
        await check_url(self.config.url, allow_http=self.config.allow_http)
        headers: dict[str, str] = dict(self.config.headers)
        if self.config.auth_bearer:
            headers["Authorization"] = f"Bearer {self.config.auth_bearer}"
        if etag := ctx.watermark.get("etag"):
            headers["If-None-Match"] = str(etag)
        if last_mod := ctx.watermark.get("last_modified"):
            headers["If-Modified-Since"] = str(last_mod)

        try:
            response = await self._client.request(
                self.config.method,
                self.config.url,
                headers=headers,
                auth=self.config.auth_basic,
            )
        except httpx.TimeoutException as exc:
            raise TransientError(f"timeout fetching {self.config.url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TransientError(f"http error fetching {self.config.url}: {exc}") from exc

        if response.status_code == 304:
            return
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            seconds: float | None = None
            if retry_after:
                try:
                    seconds = float(retry_after)
                except ValueError:
                    seconds = None
            raise RateLimited(f"429 on {self.config.url}", retry_after=seconds)
        if 500 <= response.status_code < 600:
            raise TransientError(
                f"upstream {response.status_code} on {self.config.url}"
            )
        if response.status_code >= 400:
            raise PermanentError(
                f"client error {response.status_code} on {self.config.url}"
            )

        body = response.content
        if len(body) > self.config.max_bytes:
            raise PermanentError(
                f"payload exceeds max_bytes ({len(body)} > {self.config.max_bytes})"
            )

        if self.config.decompress == "gzip":
            body = gzip.decompress(body)
        elif self.config.decompress == "zip":
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                names = zf.namelist()
                target = self.config.zip_member or (names[0] if names else None)
                if target is None:
                    raise PermanentError("zip archive empty")
                body = zf.read(target)

        ctx.watermark["etag"] = response.headers.get("ETag")
        ctx.watermark["last_modified"] = response.headers.get("Last-Modified")

        yield RawPayload(
            body=body,
            content_type=response.headers.get("Content-Type", self.default_content_type),
            headers=dict(response.headers),
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            source_url=self.config.url,
        )

    def post_process(self, raw: RawPayload) -> RawPayload:  # noqa: PLR6301
        return raw

    @staticmethod
    def _maybe_payload(_: dict[str, Any]) -> None:
        return None
