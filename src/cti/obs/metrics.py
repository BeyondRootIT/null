"""Prometheus metrics. Names align with the plan; labels stay low-cardinality."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

RECORDS_IN = Counter(
    "cti_records_in_total",
    "Records entering a stage from the previous one",
    labelnames=("source", "stage"),
    registry=REGISTRY,
)

RECORDS_OUT = Counter(
    "cti_records_out_total",
    "Records emitted by a publisher",
    labelnames=("source", "publisher"),
    registry=REGISTRY,
)

FETCH_BYTES = Counter(
    "cti_fetch_bytes_total",
    "Raw bytes fetched from upstream",
    labelnames=("source",),
    registry=REGISTRY,
)

FETCH_SECONDS = Histogram(
    "cti_fetch_seconds",
    "Time spent in the fetch stage",
    labelnames=("source",),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    registry=REGISTRY,
)

PARSE_ERRORS = Counter(
    "cti_parse_errors_total",
    "Records dropped due to parse errors",
    labelnames=("source",),
    registry=REGISTRY,
)

DROPPED = Counter(
    "cti_dropped_total",
    "Records dropped (enricher returned None, TLP, etc.)",
    labelnames=("source", "reason"),
    registry=REGISTRY,
)

QUEUE_DEPTH = Gauge(
    "cti_queue_depth",
    "Inter-stage queue depth",
    labelnames=("stage",),
    registry=REGISTRY,
)

CIRCUIT_STATE = Gauge(
    "cti_circuit_state",
    "0=closed, 1=half-open, 2=open",
    labelnames=("source",),
    registry=REGISTRY,
)

DLQ_TOTAL = Counter(
    "cti_dlq_total",
    "Records moved to the dead-letter table",
    labelnames=("source", "reason"),
    registry=REGISTRY,
)

RUN_DURATION = Histogram(
    "cti_run_duration_seconds",
    "Duration of a complete feed run",
    labelnames=("source", "state"),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
    registry=REGISTRY,
)
