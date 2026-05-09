# Design decisions

A trade-off log: each entry is **the choice we made**, **the alternative we
rejected**, **why**, and **when this might flip**.

## Queue: arq + Redis (over Celery, RabbitMQ, NATS)

| Considered | Why we picked arq |
| --- | --- |
| **arq** | Pure asyncio, low-overhead, plays well with our async HTTP/DB stack. Redis is already needed for rate limits, semaphores, bloom filter — adding RabbitMQ doubles the stateful surface. |
| Celery (rejected) | Sync-first; we'd need ~100 processes to match arq's ~100 in-flight on one process. ~10× RAM. Async-first integrations next (`aiokafka`, async TAXII) would force sync↔async bridges. |
| RabbitMQ (rejected) | Wins on durable persistence and complex routing. None apply at v0 volumes (thousands/hour). |
| NATS JetStream (deferred) | The next step **if** we exceed ~50k jobs/s. Not RabbitMQ. |

## Scheduler: APScheduler 3.x with Postgres jobstore (over distributed cron)

A single-replica scheduler is a SPOF. Mitigations:

- **Now:** Postgres jobstore so the schedule recovers on restart.
- **v0.4:** leader election via Redis redlock allowing 2 hot replicas.
- **v1.0+:** evaluate `kubernetes.cron` jobs as an alternative if the cluster
  story matures.

## Canonical store: Postgres only (over Postgres + Elastic / OpenSearch)

GIN + `pg_trgm` covers the v0 query needs (lookup by type+value, tag search,
fuzzy on value). Two stores doubles operational complexity for no current
benefit. Re-evaluate at v0.6 if `LIKE '%foo%'` queries dominate the workload.

## Dedup: bloom is **advisory**, DB UNIQUE is authoritative

A bloom filter has false positives. Treating bloom-positive as "drop" silently
loses indicators (with `fp=0.001` over 100M records: ~100k false drops). So
bloom is only a **DB-roundtrip cache** — on bloom-positive we still hit the
DB. UPSERT on the unique constraint `(type, value)` is the source of truth.
Bloom may be ripped out entirely if benchmarks show UPSERT alone is fast
enough.

## Wire format: Pydantic-derived JSON for Kafka (no STIX/Avro/Protobuf in v0)

STIX 2.1 export will be a future *publisher transformation*, not the
canonical format. Avro/Protobuf can land in v0.1 if Kafka subscribers
demand it; nothing in the model is JSON-specific.

## Watermarks: on `feed_runs`, not `sources`

Storing the watermark on each run row means we can replay to any prior point
exactly (e.g. when fixing a parser bug). The `sources` row caches the
**latest successful** watermark for the scheduler's convenience. Common
watermark fields (`last_etag`, `last_modified`, `last_seen_id`) are promoted
to columns so alerting like "no source advanced its watermark in 1h" is a
trivial query.

## Plugin model: entry points (over file-drops or `importlib` scanning)

Entry points are declarative in `pyproject.toml`, version-pinned, type-checked
at install, and friendly to future sandboxing (a permissions manifest can
live next to the entry-point declaration).

## Egress: allowlist on by default

The most obvious foot-gun for an ingestion framework is being weaponized into
an SSRF tunnel. Plain HTTP is rejected unless explicitly enabled per source;
RFC1918 / metadata IPs are blocked unconditionally.

## Migrations: explicit, never on app startup

`cti db migrate` is a one-shot job, not a step in the worker entrypoint.
This forces operators to think about expand-then-contract during rolling
deploys and prevents two replicas from racing on schema changes.

## Sync-bridge for plugin authors

The framework is asyncio internally, but ~80% of plugin code is sync. We
expose `SyncParser` / `SyncEnricher` ABCs that `asyncio.to_thread` the
sync hooks. Async is **opt-in** for the cases that need it (paginated REST,
SSE, websockets, native async drivers).

## Time semantics: `_by_us` vs source-claimed

`first_seen_by_us` / `last_seen_by_us` answer "when did our system see this?".
`valid_from` / `valid_until` answer "when does the source say this is valid?".
Conflating them produces wrong reports — keeping both columns named
explicitly prevents that.

## Test isolation: testcontainers, not fixtures

Integration tests spin a real Postgres via `testcontainers[postgres]`,
marked `integration`. Fast unit tests don't touch the DB. Contract tests
verify every entry-point class implements its ABC and declares `name` +
`config_model`.
