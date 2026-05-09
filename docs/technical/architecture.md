# Architecture

## Pipeline

```
Discover -> Fetch -> Parse -> Normalize -> Enrich -> Dedup -> Persist -> Publish
```

Each stage is an `async def` task connected to the next via a bounded
`asyncio.Queue` (`cti.core.queue.StageQueue`). All seven run concurrently inside
one `asyncio.TaskGroup` (`cti.core.pipeline.Pipeline`). Backpressure is implicit:
a slow downstream stage blocks `put()` upstream.

| Stage | Input | Output | Module |
| --- | --- | --- | --- |
| Fetch | `RunContext` | `RawPayload` | `core/stages/fetch.py` |
| Parse | `RawPayload` | `dict[str, Any]` | `core/stages/parse.py` |
| Normalize | `dict[str, Any]` | `(Indicator, dict)` | `core/stages/normalize.py` |
| Enrich | `(Indicator, dict)` | `(Indicator, dict)` (or drop) | `core/stages/enrich.py` |
| Dedup | `(Indicator, dict)` | `(Indicator, dict)` | `core/stages/dedup.py` |
| Persist | `(Indicator, dict)` | `(Indicator, Observation)` | `core/stages/persist.py` |
| Publish | `(Indicator, Observation)` | sink | `core/stages/publish.py` |

**Persist is the durability fence.** Anything that crosses it is durable in
Postgres via idempotent UPSERT keyed on `indicator_uuid` (`uuid5(NS, "type:canonical_value")`).
Anything before it is replayable from the raw archive (see [`replay.md`](./replay.md)).

## Manager

The framework's "perfectly executed" core, in `src/cti/manager/`:

| Component | File | Role |
| --- | --- | --- |
| `SourceRegistry` | `registry.py` | Loads/validates `sources.yaml`, resolves `${env:VAR}` and `${file:/path}` refs. |
| `Scheduler` | `scheduler.py` | APScheduler 3.x with Postgres jobstore; one replica; enqueues `run_feed` arq jobs on cron + jitter. |
| `Worker` | `worker.py` | `arq` worker definition (`WorkerSettings`); executes `FeedRunner.execute(source)`. |
| `FeedRunner` | `runner.py` | Per-feed orchestrator: state row, retry, breaker, DLQ on permanent error. |
| `state.py` | `state.py` | `feed_runs` state machine (PENDING → RUNNING → SUCCESS / PARTIAL / FAILED). |
| `retry.py` | `retry.py` | `tenacity` exponential backoff; retries `TransientError` + `RateLimited` only. |
| `circuit_breaker.py` | `circuit_breaker.py` | Per-source 3-state breaker (closed → open → half-open). |
| `concurrency.py` | `concurrency.py` | Process-local global + per-source semaphores. |
| `deadletter.py` | `deadletter.py` | Persists permanent failures + traceback into `dead_letters`. |

## Processes

| Process | Replicas (v0) | Purpose |
| --- | --- | --- |
| `cti scheduler` | 1 | APScheduler service. SPOF until v0.4 leader election. |
| `cti worker` | N | arq workers consuming `cti:queue`. |
| `cti api` | 1+ | Read+trigger HTTP API + `/healthz`/`/readyz`/`/metrics`. |
| `migrate` | one-shot | `cti db migrate` (alembic upgrade head). |

In `docker-compose.yml` these are `app-scheduler`, `app-worker` (replicas: 2),
`app-api`, `migrate`.

## Why these boundaries

- **Stages are logically separate today, physically separate tomorrow.** Every
  inter-stage payload is serializable (`bytes` + headers, `dict`, Pydantic
  models), so promoting any boundary to a cross-process queue at v0.6 is a
  transport swap, not a redesign.
- **One canonical record type** (`Indicator` + `Observation`) flows end-to-end —
  no per-source schema variants downstream.
- **Plugins never touch the manager.** They implement four small ABCs; the
  framework owns scheduling, retry, breaker, dedup, persistence, observability.
