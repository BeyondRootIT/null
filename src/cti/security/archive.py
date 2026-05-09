"""Raw payload archive — writes Fetch output to S3/MinIO so replay can skip Fetch."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Protocol

from cti.core.models import RawPayload, RunContext


class RawArchive(Protocol):
    async def put(self, ctx: RunContext, payload: RawPayload) -> str:
        """Persist `payload` and return its URI."""

    async def get(self, uri: str) -> bytes: ...


class FilesystemArchive:
    """Local-filesystem archive used in dev / single-node compose. Async via to_thread."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def put(self, ctx: RunContext, payload: RawPayload) -> str:
        from asyncio import to_thread

        rel = self._key(ctx, payload)
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        await to_thread(target.write_bytes, gzip.compress(payload.body))
        return f"file://{target.resolve()}"

    async def get(self, uri: str) -> bytes:
        from asyncio import to_thread

        path = uri.removeprefix("file://")
        data = await to_thread(Path(path).read_bytes)
        return gzip.decompress(data)

    @staticmethod
    def _key(ctx: RunContext, payload: RawPayload) -> str:
        tag = (payload.etag or payload.fetched_at.strftime("%Y%m%dT%H%M%SZ")).strip(
            '"'
        ).replace("/", "_")
        return f"{ctx.source_id}/{ctx.run_id}/{tag}.bin.gz"


class S3Archive:
    """boto3-based S3/MinIO archive."""

    def __init__(self, bucket: str, prefix: str = "raw", endpoint_url: str | None = None) -> None:
        import boto3  # type: ignore[import-untyped]

        self._bucket = bucket
        self._prefix = prefix
        self._client = boto3.client("s3", endpoint_url=endpoint_url)

    async def put(self, ctx: RunContext, payload: RawPayload) -> str:
        from asyncio import to_thread

        key = (
            f"{self._prefix}/{ctx.source_id}/{ctx.run_id}/"
            f"{payload.etag or payload.fetched_at.strftime('%Y%m%dT%H%M%SZ')}.bin.gz"
        )
        await to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=gzip.compress(payload.body)
        )
        return f"s3://{self._bucket}/{key}"

    async def get(self, uri: str) -> bytes:
        from asyncio import to_thread

        rest = uri.removeprefix("s3://")
        bucket, _, key = rest.partition("/")
        obj = await to_thread(self._client.get_object, Bucket=bucket, Key=key)
        return gzip.decompress(obj["Body"].read())
