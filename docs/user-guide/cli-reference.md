# CLI reference

All commands accept `--help`. Every command reads `CTI_RUN_SOURCES_FILE`
(default `config/sources.yaml`) and the `CTI_DB_*` / `CTI_REDIS_*` env vars
where applicable.

```
cti --help
```

## Source operations

| Command | Purpose |
| --- | --- |
| `cti list-sources` | List every source from `sources.yaml`: id, plugin, schedule, enabled. |
| `cti validate-config` | Parse `sources.yaml` strictly; exit 0 on success, 2 on failure. |
| `cti show-effective-config <id>` | Pydantic-resolved config for one source, secrets masked. |
| `cti show-config` | Framework-wide Settings (env), secrets masked. |
| `cti plugins` | List discovered entry points by group. |

## Run management

| Command | Purpose |
| --- | --- |
| `cti run-once <id>` | Synchronously execute one feed run in this process — bypasses scheduler/worker. Best for development. |
| `cti backfill <id> --since <ISO>` | Wipe the source's watermark, then `run-once`. Forces a full re-pull. |
| `cti replay <run_id> [--from-stage parse\|normalize\|enrich\|persist]` | Replay a previous run from its archived raw payload. |

## Long-running processes

| Command | Purpose |
| --- | --- |
| `cti scheduler` | APScheduler service. Single replica. |
| `cti worker` | arq worker. Run with `--max-jobs N` etc via `CTI_WORKER_*` env vars. |
| `cti api [--host HOST] [--port PORT]` | ASGI app: `/healthz`, `/readyz`, `/metrics`, `/v1/*`. |

## Database

| Command | Purpose |
| --- | --- |
| `cti db migrate` | `alembic upgrade head`. One-shot job. |
| `cti db ensure-partitions [--months N]` | Create missing monthly partitions for `indicator_observations`. Default 3. |

## Dead-letter queue

| Command | Purpose |
| --- | --- |
| `cti dlq list [--source X] [--all]` | Recent dead-letters; default hides already-replayed. |
| `cti dlq show <id>` | Full row including traceback (JSON). |
| `cti dlq replay <id>` | Mark replayed (no actual retry yet — v0.1). |

## Examples

```bash
# Validate before deploying
cti validate-config

# Run a feed locally end-to-end
cti run-once abuse_ch_urlhaus

# Force a full re-pull of the last 7 days
cti backfill abuse_ch_urlhaus --since 2026-05-01T00:00:00Z

# Replay a past run from raw bytes (after parser bug fix)
cti replay 4a3a2... --from-stage parse

# Boot the API for an integration on :8080
cti api --host 0.0.0.0 --port 8080
```
