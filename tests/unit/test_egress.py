from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from cti.core.errors import EgressBlocked
from cti.security.egress import check_url


def _gai(addr: str):
    async def fake(*args, **kwargs):
        return [(0, 0, 0, "", (addr, 0))]

    loop = asyncio.get_event_loop()
    return patch.object(loop, "getaddrinfo", side_effect=fake)


@pytest.mark.asyncio
async def test_blocks_metadata_ip():
    with _gai("169.254.169.254"):
        with pytest.raises(EgressBlocked):
            await check_url("http://example.com/x", allow_http=True)


@pytest.mark.asyncio
async def test_blocks_loopback():
    with _gai("127.0.0.1"):
        with pytest.raises(EgressBlocked):
            await check_url("http://example.com/x", allow_http=True)


@pytest.mark.asyncio
async def test_rejects_plain_http_by_default():
    with pytest.raises(EgressBlocked):
        await check_url("http://example.com/x", allow_http=False)


@pytest.mark.asyncio
async def test_allows_public_https():
    with _gai("8.8.8.8"):
        await check_url("https://example.com/x")
