# Tutorial 1 — Getting started

You'll bring up the full stack with Docker Compose and ingest URLhaus
end-to-end. ~10 minutes.

## Prerequisites

- Docker + Docker Compose
- Outbound network access to `urlhaus.abuse.ch`

## Step 1 — Bootstrap the config

```bash
cd cti
cp config/sources.example.yaml config/sources.yaml
cp secrets/api_tokens.example.yaml secrets/api_tokens.yaml
```

Edit `secrets/api_tokens.yaml` and replace `change-me-readonly` /
`change-me-trigger` with strong random strings.

## Step 2 — Bring the stack up

```bash
docker compose --profile obs up -d
```

This starts: Postgres, Redis, scheduler, 2× workers, API, Prometheus, Grafana.

Wait ~10 seconds, then run the migration job:

```bash
docker compose run --rm migrate
# expect: "INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial"
```

## Step 3 — Verify the install

```bash
docker compose exec app-worker cti plugins
```

You should see all four entry-point groups populated.

```bash
docker compose exec app-worker cti validate-config
# OK: 2 sources

curl -fsS http://localhost:8080/healthz
# ok

curl -fsS http://localhost:8080/readyz
# ready
```

## Step 4 — Run a feed once

`cti run-once` executes the pipeline synchronously in the worker container,
bypassing the scheduler — fastest way to see end-to-end behaviour.

```bash
docker compose exec app-worker cti run-once abuse_ch_urlhaus
```

Tail the logs:

```bash
docker compose logs -f app-worker
```

You'll see structured JSON like:

```json
{"event": "run.complete", "level": "info", "run_id": "...",
 "source_id": "abuse_ch_urlhaus", "state": "SUCCESS"}
```

## Step 5 — Confirm data landed

```bash
docker compose exec postgres psql -U cti_user -d cti -c \
  "SELECT count(*) FROM cti.indicators WHERE type='url'"
```

Should be a non-zero number (URLhaus typically has 5–30k entries).

```bash
docker compose exec postgres psql -U cti_user -d cti -c \
  "SELECT state, records_in, records_out FROM cti.feed_runs
   WHERE source_id='abuse_ch_urlhaus' ORDER BY started_at DESC LIMIT 1"
```

## Step 6 — Query via the HTTP API

```bash
TOKEN=$(grep -A1 'name: "operator-readonly"' secrets/api_tokens.yaml | head -1 | awk '{print $3}' | tr -d '"')

curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/v1/sources

curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/v1/runs?source=abuse_ch_urlhaus" | head
```

## Step 7 — Inspect metrics

```bash
curl -fsS http://localhost:8080/metrics | grep '^cti_'
```

Open Grafana at <http://localhost:3000> (anonymous Admin); add a Prometheus
datasource pointing at `http://prometheus:9090`.

## Step 8 — Trigger via the API

```bash
TRIGGER_TOKEN=...   # the one with scopes [read, trigger]
curl -fsS -X POST -H "Authorization: Bearer $TRIGGER_TOKEN" \
  http://localhost:8080/v1/sources/abuse_ch_feodo_tracker/trigger
```

The scheduler's cron will also fire on its own — this just kicks one off
manually.

## Next steps

- [Tutorial 2](./02-add-a-source.md) — add your own HTTP feed.
- [Tutorial 3](./03-write-a-plugin.md) — ship a custom plugin.
- [Operations guide](../user-guide/operations.md) — DLQ, replay, partitions.
