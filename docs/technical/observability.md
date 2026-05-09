# Observability

Three pillars: structured JSON logs, Prometheus metrics, OpenTelemetry traces.
Modules in `src/cti/obs/`.

## Logs

`structlog` produces JSON in production (`CTI_OBS_LOG_JSON=true`, default) or
key=value in dev. Bound contextvars for `run_id` and `source_id` propagate
automatically across stages within one run via
`cti.obs.logging.bind_run_context(run_id, source_id)`.

Sample line:

```json
{"event": "run.complete", "level": "info", "timestamp": "2026-05-09T12:34:56Z",
 "run_id": "...", "source_id": "abuse_ch_urlhaus", "state": "SUCCESS"}
```

Configure verbosity with `CTI_OBS_LOG_LEVEL=DEBUG|INFO|WARN|ERROR`.

## Metrics

Exposed by the API process at `:8080/metrics`. Defined in
`src/cti/obs/metrics.py` against a private `CollectorRegistry`.

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `cti_records_in_total` | Counter | `source`, `stage` | Records entering a stage. |
| `cti_records_out_total` | Counter | `source`, `publisher` | Records emitted by a publisher. |
| `cti_fetch_bytes_total` | Counter | `source` | Raw bytes fetched. |
| `cti_fetch_seconds` | Histogram | `source` | Fetch-stage duration. |
| `cti_parse_errors_total` | Counter | `source` | Parse-stage failures. |
| `cti_dropped_total` | Counter | `source`, `reason` | Records dropped (`enricher`, `tlp:<publisher>`). |
| `cti_queue_depth` | Gauge | `stage` | Current depth of inter-stage queue. |
| `cti_circuit_state` | Gauge | `source` | 0=closed, 1=half-open, 2=open. |
| `cti_dlq_total` | Counter | `source`, `reason` | New rows in `dead_letters`. |
| `cti_run_duration_seconds` | Histogram | `source`, `state` | End-to-end run duration. |

Plugin-emitted metrics are auto-prefixed `cti_plugin_<plugin_name>_*` (see
`Plugin.metrics()` in [`plugin-sdk.md`](./plugin-sdk.md)).

## Tracing

OpenTelemetry SDK with OTLP/gRPC exporter. Disabled by default; set
`CTI_OBS_OTEL_ENDPOINT=http://otel-collector:4317` to enable.
`cti.obs.tracing.tracer()` returns a tracer named `cti`; per-stage spans are
the recommended pattern but not yet wired in v0.

## Health checks

| Endpoint | Status |
| --- | --- |
| `GET /healthz` | Always 200 if process is alive. |
| `GET /readyz` | 200 only if a DB session can be opened; 503 otherwise. |
| `GET /metrics` | Prometheus exposition (text/plain). |

## Suggested alerts

- `cti_circuit_state{source="X"} == 2` for > 5 m → upstream is down or rate-limiting hard.
- `rate(cti_dlq_total[5m]) > 1` → a new permanent failure is recurring.
- `time() - max by (source) (cti_records_out_total / on(source) cti_records_out_total)`
  is too clever; instead alert on `absent_over_time(cti_records_out_total{source="X"}[2h])`
  → source X stopped producing.
- `cti_queue_depth{stage="parse"}` saturating its `maxsize` → CPU-bound parser
  blocking the loop; consider scaling workers.
