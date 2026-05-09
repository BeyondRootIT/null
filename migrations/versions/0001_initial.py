"""initial cti schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-09

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cti")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "sources",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256)),
        sa.Column("plugin", sa.String(128), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("watermark", sa.JSON, server_default="{}"),
        sa.Column("last_etag", sa.String(256)),
        sa.Column("last_modified", sa.String(64)),
        sa.Column("last_seen_id", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="cti",
    )

    op.create_table(
        "feed_runs",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column(
            "source_id",
            sa.String(128),
            sa.ForeignKey("cti.sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_bytes", sa.BigInteger, server_default="0"),
        sa.Column("records_in", sa.BigInteger, server_default="0"),
        sa.Column("records_out", sa.BigInteger, server_default="0"),
        sa.Column("parse_errors", sa.Integer, server_default="0"),
        sa.Column("dropped", sa.Integer, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("watermark", sa.JSON, server_default="{}"),
        sa.Column("raw_uri", sa.String(1024)),
        schema="cti",
    )
    op.create_index(
        "idx_feed_runs_source_started",
        "feed_runs",
        [sa.text("source_id"), sa.text("started_at DESC")],
        schema="cti",
    )
    op.create_index("idx_feed_runs_state", "feed_runs", ["state"], schema="cti")

    op.create_table(
        "indicators",
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("pattern", sa.Text),
        sa.Column("confidence", sa.Integer, server_default="50"),
        sa.Column("severity", sa.String(16), server_default="info"),
        sa.Column("tlp", sa.String(16), server_default="AMBER"),
        sa.Column("tags", sa.ARRAY(sa.Text), server_default="{}"),
        sa.Column("first_seen_by_us", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_by_us", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("schema_version", sa.String(8), server_default="1"),
        sa.UniqueConstraint("type", "value", name="uq_indicators_type_value"),
        schema="cti",
    )
    op.create_index("idx_indicators_type", "indicators", ["type"], schema="cti")
    op.execute("CREATE INDEX idx_indicators_tags ON cti.indicators USING GIN (tags)")
    op.execute(
        "CREATE INDEX idx_indicators_value_trgm ON cti.indicators "
        "USING GIN (value gin_trgm_ops)"
    )

    # Partitioned observations table.
    op.execute(
        """
        CREATE TABLE cti.indicator_observations (
            id          BIGSERIAL,
            indicator_id UUID NOT NULL,
            source_id    VARCHAR(128) NOT NULL,
            feed_run_id  UUID NOT NULL,
            observed_at  TIMESTAMPTZ NOT NULL,
            tlp          VARCHAR(16) NOT NULL,
            confidence   INTEGER NOT NULL,
            raw          JSONB NOT NULL DEFAULT '{}',
            schema_version VARCHAR(8) NOT NULL DEFAULT '1',
            PRIMARY KEY (observed_at, id)
        ) PARTITION BY RANGE (observed_at)
        """
    )
    op.execute(
        "CREATE INDEX idx_obs_indicator_id ON cti.indicator_observations (indicator_id)"
    )
    op.execute("CREATE INDEX idx_obs_source ON cti.indicator_observations (source_id)")
    op.execute("CREATE INDEX idx_obs_run ON cti.indicator_observations (feed_run_id)")

    # Bootstrap partitions for current + next 2 months.
    op.execute(
        """
        DO $$
        DECLARE
            d DATE := date_trunc('month', NOW())::DATE;
            i INT;
            start_d DATE;
            end_d DATE;
            tname TEXT;
        BEGIN
            FOR i IN 0..2 LOOP
                start_d := (d + (i || ' month')::INTERVAL)::DATE;
                end_d := (d + ((i+1) || ' month')::INTERVAL)::DATE;
                tname := 'indicator_observations_' || to_char(start_d, 'YYYY_MM');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS cti.%I PARTITION OF cti.indicator_observations '
                    'FOR VALUES FROM (%L) TO (%L)', tname, start_d, end_d);
            END LOOP;
        END$$;
        """
    )

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("feed_run_id", sa.UUID, nullable=False, index=True),
        sa.Column("source_id", sa.String(128), nullable=False, index=True),
        sa.Column("payload_sha", sa.String(64), nullable=False),
        sa.Column("error_class", sa.String(128), nullable=False),
        sa.Column("error_msg", sa.Text, nullable=False),
        sa.Column("traceback", sa.Text, nullable=False),
        sa.Column("reason", sa.String(64), server_default="permanent"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("replayed_at", sa.DateTime(timezone=True)),
        schema="cti",
    )


def downgrade() -> None:
    op.drop_table("dead_letters", schema="cti")
    op.execute("DROP TABLE IF EXISTS cti.indicator_observations CASCADE")
    op.drop_table("indicators", schema="cti")
    op.drop_table("feed_runs", schema="cti")
    op.drop_table("sources", schema="cti")
    op.execute("DROP SCHEMA IF EXISTS cti CASCADE")
