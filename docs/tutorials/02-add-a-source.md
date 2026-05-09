# Tutorial 2 — Add a new HTTP source

You'll add a new feed using only `sources.yaml` and shipped plugins. No
Python required. ~15 minutes.

We'll use **FireHOL Level 1** (a public list of bad IPs as a plaintext file)
as our example.

## Step 1 — Pick the right shipped plugins

| Aspect | Pick |
| --- | --- |
| Transport: HTTPS GET, plain text body | `http_txt_lines` connector |
| Format: one IP / CIDR per line, `#` comments | `txt` parser |
| What we want: drop private IPs | `allowlist` enricher |
| Where to write: canonical store | `postgres` publisher |

## Step 2 — Write the source entry

Append to `config/sources.yaml`:

```yaml
  - id: firehol_level1
    name: "FireHOL Level 1"
    plugin: http_txt_lines
    parser: txt
    enrichers: [allowlist]
    publishers: [postgres]
    schedule: "30 */6 * * *"     # 6h cadence, offset to avoid stampede
    rate_limit_rps: 1.0
    timeout_seconds: 60
    tlp: GREEN
    confidence_default: 75
    tags: ["firehol", "level1"]
    params:
      url: "https://iplists.firehol.org/files/firehol_level1.netset"
    parser_params:
      extract: ["ipv4"]
      skip_comment_prefix: "#"
      expand_cidrs: false        # keep CIDRs as a single indicator
    normalize:
      type_field: type           # the txt parser emits {"type": "ipv4", "value": "..."}
      value_field: value
      static_tags: ["firehol", "level1"]
      tlp_default: GREEN
      confidence_default: 75
    enricher_params:
      allowlist:
        drop_private_ips: true
```

## Step 3 — Validate

```bash
docker compose exec app-worker cti validate-config
# OK: 3 sources
```

If the YAML doesn't validate, the CLI prints a clear pydantic error pointing
at the offending field.

## Step 4 — Inspect the effective config

```bash
docker compose exec app-worker cti show-effective-config firehol_level1
```

The output is the Pydantic-resolved `SourceConfig` JSON, with secrets masked.
Eyeball it before running.

## Step 5 — Run it once

```bash
docker compose exec app-worker cti run-once firehol_level1
```

Logs will show fetch → parse → normalize → publish. Verify rows landed:

```sql
SELECT count(*) FROM cti.indicators
  WHERE 'firehol' = ANY(tags);
```

## Step 6 — Hand off to the scheduler

The scheduler picks up new `sources.yaml` entries on startup. Reload it:

```bash
docker compose restart app-scheduler
docker compose logs --tail 50 app-scheduler | grep firehol_level1
# enqueued run_feed source=firehol_level1 ...
```

(Hot-reload of `sources.yaml` is on the v0.1 roadmap.)

## What just happened

You composed three off-the-shelf plugins via configuration and got a
fully-managed feed: scheduling, retries on transient failures, circuit
breaking, rate limiting, dedup, persistence, observability — for free.

## Tweaks worth knowing

- **CIDR expansion**: set `parser_params.expand_cidrs: true` to write each
  host individually (be careful — `/8` networks are huge).
- **Per-host rate limit**: lower `rate_limit_rps` if FireHOL flags you.
- **Conditional GET**: works automatically. The connector remembers ETag /
  Last-Modified in `feed_runs.watermark` and sends `If-None-Match` /
  `If-Modified-Since`. A 304 means "no work to do" — it's logged but doesn't
  count as failure.
- **TLP**: leave at `GREEN` for FireHOL (it's public). Changing it later
  only affects new observations; existing rows keep their stamped TLP.
