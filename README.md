# CTI — Cyber Threat Intelligence Data Ingestion Framework

A plugin-extensible framework that pulls indicators from heterogeneous CTI sources, normalizes,
enriches, deduplicates, and persists them to a canonical store, with first-class orchestration
(scheduling, retries, rate limits, circuit breaking, observability).

## Quick start

```bash
uv sync --extra dev
cp config/sources.example.yaml config/sources.yaml
docker compose --profile obs up -d
docker compose run --rm migrate
docker compose exec app-worker cti plugins
docker compose exec app-worker cti run-once abuse_ch_urlhaus
```

## Architecture

```
Discover -> Fetch -> Parse -> Normalize -> Enrich -> Dedup -> Persist -> Publish
```

Each stage is an `async` task with a typed input/output, connected by bounded `asyncio.Queue`s.
One canonical record type (`Indicator` + `Observation`) flows end-to-end.

### Plugins

Four ABCs discovered via Python entry points (`cti.connectors`, `cti.parsers`,
`cti.enrichers`, `cti.publishers`). Plugin authors mostly write **sync code** —
the framework owns the asyncio machinery via sync-bridge base classes.

### Manager

Source registry, APScheduler with Postgres jobstore, arq workers, per-feed state machine,
exponential-backoff retry, per-source circuit breaker, per-host token-bucket rate limit,
SSRF egress guard, structured logs / Prometheus metrics / OpenTelemetry tracing.

### Interaction

CLI (`cti …`) and HTTP API on `/v1/*`. Static bearer tokens with scopes (`read`, `trigger`,
`admin`); no anonymous access.

## Layout

```
src/cti/
  core/          # models, hashing, errors, ABCs, pipeline, stages, queues, ratelimit
  manager/       # registry, scheduler, worker, runner, state, retry, breaker, deadletter
  plugins/       # loader + connectors/, parsers/, enrichers/, publishers/
  persistence/   # sqlalchemy models, repositories, partitioning
  config/        # loader, schema, secrets resolver
  obs/           # logging, metrics, tracing, ASGI app (healthz/readyz/metrics + /v1)
  security/      # egress (SSRF), TLP
  cli/           # typer commands
```

## License

Apache-2.0
