"""Async engine + session factory."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(dsn: str, **kwargs: Any) -> AsyncEngine:
    """Build the global async engine. Call once at process startup."""
    global _engine, _session_factory
    _engine = create_async_engine(
        dsn,
        pool_size=kwargs.pop("pool_size", 5),
        max_overflow=kwargs.pop("max_overflow", 10),
        pool_pre_ping=True,
        future=True,
        **kwargs,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("db engine not initialized; call init_engine() first")
    return _engine


@contextlib.asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("db engine not initialized")
    async with _session_factory() as session:
        yield session


async def dispose() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
