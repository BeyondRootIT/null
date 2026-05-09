# Operations

Day-2 operations: scaling, partitions, DLQ, replay, backups.

## Scaling

| Workload | Scale by |
| --- | --- |
| Many small feeds, network-bound | More `cti worker` replicas. |
| Few huge JSON feeds, CPU-bound parse | More `cti worker` replicas; raise `CTI_RUN_GLOBAL_CONCURRENCY` per-worker if RAM allows. |
| API request volume | More `cti api` replicas behind a load balancer. The API is stateless. |
| Postgres write throughput (`> 25k records/s`) | Switch persist stage to COPY-into-staging-table approach (see roadmap), or shard horizontally at v1.0. |

Scheduler **must remain replicas: 1** until v0.4 leader election lands.

## Database partitions

`indicator_observations` is monthly-partitioned by `observed_at`. Migration
`0001_initial` creates partitions for the current month plus the next two.
**Run `cti db ensure-partitions --months 3` on a monthly cron** to roll the
window forward; the included `docker-compose.yml` does not yet do this — add a
sidecar CronJob in your deploy.

```
0 0 1 * *  cti db ensure-partitions --months 3
```

Without future partitions, inserts after the last bound start failing.

## Dead letter queue

Permanent errors land in `cti.dead_letters` with a full traceback.

```bash
cti dlq list                          # 200 most-recent unreplayed
cti dlq list --source abuse_ch_urlhaus
cti dlq show 42                       # full row + traceback
cti dlq replay 42                     # mark replayed (v0)
```

Watch `cti_dlq_total` rate. A sudden spike means a parser broke or upstream
contract changed.

## Replay

Two scenarios:

1. **Parser bug fix.** You shipped a buggy parser; you now want to re-run
   yesterday's feed runs against the corrected parser, without re-fetching.

   ```bash
   for r in $(cti list-recent-runs --source X --since 2026-05-08); do
     cti replay "$r" --from-stage parse
   done
   ```

   (Yes, that helper doesn't exist yet — for now query `feed_runs` directly:
   `SELECT id FROM cti.feed_runs WHERE source_id = 'X' AND state = 'SUCCESS'`.)

2. **Re-publish to a new sink.** You added a Kafka publisher and want to
   backfill the last week's indicators. Replay from `--from-stage persist`
   re-issues UPSERTs (idempotent) and runs the publish stage again.

See [`technical/replay.md`](../technical/replay.md) for the model.

## Watermarks

`feed_runs.watermark` (JSONB) holds whatever the source's connector wants:
ETag, Last-Modified, last-seen-id, opaque cursor. `sources.watermark` mirrors
the most recent SUCCESS for the scheduler. To force a full re-pull:

```bash
cti backfill <source_id> --since 2026-05-01T00:00:00Z
```

This wipes the source's watermark and runs once.

## Postgres maintenance

- `VACUUM ANALYZE cti.indicators;` after large backfills.
- `REINDEX INDEX idx_indicators_value_trgm;` if trigram queries get slow.
- Snapshot backups via `pg_basebackup` or your managed PG provider.
  `indicator_observations` partitions can be archived to cold storage and
  detached after, e.g., 90 days; see Postgres `ALTER TABLE … DETACH PARTITION`.

## Logs and traces

JSON logs to stdout; ship via Vector / Fluent Bit. OTel traces via OTLP/gRPC
when `CTI_OBS_OTEL_ENDPOINT` is set — point at your collector.

## Capacity planning

Per worker, on a modern CPU (figures from the design plan):

| Stage | Throughput |
| --- | --- |
| CSV parse | ~100k rows/s |
| JSON parse | ~25k records/s (stdlib) |
| Normalize + uuid5 | ~100k/s |
| Enrich (defang/allowlist) | ~500k/s |
| Postgres UPSERT (batch 1000) | ~15–25k/s **(bottleneck)** |

End-to-end with 4 workers: ~60–100k records/s sustained.
