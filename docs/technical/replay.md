# Replay model

## What you can resume, and from where

| After this stage crashes | You can resume from… | Why |
| --- | --- | --- |
| Fetch | the upstream URL (re-fetch) **or** the raw archive (Parse). | We keep the gzipped raw bytes in object storage. |
| Parse | the raw archive (Normalize). | Same archived bytes, re-parsed. |
| Normalize | the raw archive (Enrich, w/ a fresh parse). | We don't checkpoint between Normalize and Enrich. |
| Enrich | the raw archive. | Same. |
| Persist | nothing extra needed. | UPSERT is idempotent on `indicator_uuid`. |
| Publish (extra publishers) | the run's `(indicator, observation)` pairs in DB. | Persist already happened. |

**Persist is the durability fence.** Anything past it is in Postgres; anything
before it is replayable from the archive.

## Raw payload archive

Default-on, two backends. Configured via `CTI_ARCHIVE_*` env vars.

| Backend | Trigger | Notes |
| --- | --- | --- |
| `filesystem` (default) | `CTI_ARCHIVE_BACKEND=filesystem` + `CTI_ARCHIVE_ROOT=/var/lib/cti/raw` | Gzipped files at `<root>/<source_id>/<run_id>/<etag-or-timestamp>.bin.gz`. Good for single-node compose. |
| `s3` | `CTI_ARCHIVE_BACKEND=s3` + `CTI_ARCHIVE_BUCKET=cti-raw` (+ optional `CTI_ARCHIVE_ENDPOINT_URL` for MinIO) | Object key: `<prefix>/<source_id>/<run_id>/<etag>.bin.gz`. |

Each successful Fetch writes a copy and stamps `feed_runs.raw_uri` with the
archive URI. Replay reads from there.

> **Why default-on.** Many feeds rotate hourly. By the time you debug a parser
> issue at noon, the URL that produced the 9am bug returns different bytes.
> Without a raw archive, the only "replay" is "re-fetch", which won't reproduce
> the bug.

## `cti replay <run_id>`

```
cti replay 4a3a2... --from-stage parse
```

| Flag | Default | Effect |
| --- | --- | --- |
| `--from-stage parse` | parse | Skip Fetch, read raw_uri, run Parse → Persist (and Publish). |
| `--from-stage normalize` |  | Run Normalize → Publish. |
| `--from-stage enrich` |  | Run Enrich → Publish. |
| `--from-stage persist` |  | Re-issue UPSERT only (no parsing). |

Replay reuses the same `FeedRunner` machinery, so retry/breaker/DLQ behave
the same as a normal run. The new run gets a fresh `run_id` so the original
`feed_runs` row is preserved.

## What's not in v0

- **Mid-stage checkpointing** (resume mid-batch on a worker crash) is not in
  v0. The granularity is one arq job per run; on crash, the whole run replays,
  which is safe because Persist is idempotent.
- **Cross-stage queues as durable channels** (Kafka / NATS between stages)
  is the v0.6 path. The interfaces already accept serializable payloads, so
  it's a transport swap.
