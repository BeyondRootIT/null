"""SQLAlchemy ORM models. Schema = `cti`. Partitioning of observations is by month."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "cti"


class Base(DeclarativeBase):
    metadata_args = {"schema": SCHEMA}


class SourceRow(Base):
    __tablename__ = "sources"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    plugin: Mapped[str] = mapped_column(String(128))
    config_hash: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    watermark: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    last_etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(64))
    last_seen_id: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedRunRow(Base):
    __tablename__ = "feed_runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.sources.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    records_in: Mapped[int] = mapped_column(BigInteger, default=0)
    records_out: Mapped[int] = mapped_column(BigInteger, default=0)
    parse_errors: Mapped[int] = mapped_column(Integer, default=0)
    dropped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    watermark: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
    raw_uri: Mapped[str | None] = mapped_column(String(1024))


class IndicatorRow(Base):
    __tablename__ = "indicators"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(Text)
    pattern: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(Integer, default=50)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    tlp: Mapped[str] = mapped_column(String(16), default="AMBER")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    first_seen_by_us: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_by_us: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(8), default="1")


class IndicatorObservationRow(Base):
    __tablename__ = "indicator_observations"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    indicator_id: Mapped[UUID] = mapped_column(index=True)
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    feed_run_id: Mapped[UUID] = mapped_column(index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tlp: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    schema_version: Mapped[str] = mapped_column(String(8), default="1")


class DeadLetterRow(Base):
    __tablename__ = "dead_letters"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feed_run_id: Mapped[UUID] = mapped_column(index=True)
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_sha: Mapped[str] = mapped_column(String(64))
    error_class: Mapped[str] = mapped_column(String(128))
    error_msg: Mapped[str] = mapped_column(Text)
    traceback: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(64), default="permanent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
