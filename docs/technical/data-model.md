# Data model

Defined in `src/cti/core/models.py`. All records are Pydantic v2 models and
carry an explicit `schema_version` (currently `"1"`).

## Canonical types

### `Indicator`

The deduplicated unit. UUID is **derived** from `(type, canonical_value)` via
`uuid5` — see [`hashing`](#canonicalization-and-uuid-derivation) below.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | `UUID` | `uuid5(NS, "{type}:{canonical_value}")` — never random. |
| `type` | `IndicatorType` | `ipv4`, `ipv6`, `domain`, `url`, `sha256`, `sha1`, `md5`, `email`, `file_name`, `mutex`, `registry_key`, `yara_rule`. |
| `value` | `str` | Stored canonical (lower-cased, refanged, IDN-encoded, default-port stripped). |
| `pattern` | `str?` | Free-text pattern (e.g. STIX pattern). |
| `confidence` | `int` 0–100 | |
| `severity` | `Severity` | `info`, `low`, `medium`, `high`, `critical`. |
| `tlp` | `TLP` | TLP v2.0: `CLEAR`, `GREEN`, `AMBER`, `AMBER+STRICT`, `RED`. |
| `tags` | `tuple[str, ...]` | Free-form, deduplicated. |
| `first_seen_by_us` | `datetime` (UTC) | Our first observation timestamp. |
| `last_seen_by_us` | `datetime` (UTC) | Most recent observation timestamp. |
| `valid_from` | `datetime?` | Source-claimed validity start. |
| `valid_until` | `datetime?` | Source-claimed validity end. |
| `schema_version` | `str` | Bump on backwards-incompatible changes. |

> **Time semantics.** `first_seen_by_us` / `last_seen_by_us` track *our*
> sightings; `valid_from` / `valid_until` track what the *source* claims. Don't
> conflate them — they answer different questions.

### `Observation`

A single sighting of an indicator by one source during one run. Stored in
`indicator_observations` (monthly-partitioned), so multi-source corroboration
is preserved.

| Field | Type | Notes |
| --- | --- | --- |
| `indicator_id` | `UUID` | FK to `indicators.id`. |
| `source_id` | `str` | Stable source identifier (`abuse_ch_urlhaus`). |
| `feed_run_id` | `UUID` | The `feed_runs` row that produced this observation. |
| `observed_at` | `datetime` (UTC) | Partition key. |
| `tlp` | `TLP` | Per-observation; aggregated TLP is computed at publish time. |
| `confidence` | `int` 0–100 | |
| `raw` | `dict` | Original record dict (JSONB). |
| `schema_version` | `str` | |

### `RawPayload` and `RunContext`

`RawPayload` carries fetched bytes plus headers/etag/last-modified. `RunContext`
is the shared mutable run-scoped state: run id, source id, watermark, the URI
of the archived raw payload.

## Canonicalization and UUID derivation

`src/cti/core/hashing.py`. `Indicator.build()` is the construction path:

```python
Indicator.build(indicator_type=IndicatorType.URL, value="hxxp://Evil[.]com:80/A")
```

1. `_refang` collapses `[.]`, `(.)`, `[at]`, `[://]`, `hxxp://` → real chars.
2. Per-type canonicalizer normalizes:
   - **IPv4 / IPv6**: parse via `ipaddress`; lowercase IPv6.
   - **Domain**: lowercase, strip trailing dot, IDN-encode, validate label regex.
   - **URL**: refang, lowercase scheme + netloc, strip default ports (80/443),
     drop fragment.
   - **Hashes**: lowercase hex, length-validated (32/40/64).
   - **Email**: lowercase, canonical domain on right side.
3. `uuid5(_CTI_NS, "{type}:{canonical_value}")`.

Determinism guarantee: for the same input, **across processes and across
versions**, the UUID is identical. Don't change `_CTI_NS` — it would invalidate
every existing dedup key.

## Postgres schema

```
cti.sources                 (source registry mirror, watermark cache)
cti.feed_runs               (per-run state machine)
cti.indicators              (canonical, UNIQUE(type, value))
cti.indicator_observations  (monthly-partitioned by observed_at)
cti.dead_letters            (permanent failures + traceback)
```

The initial migration (`migrations/versions/0001_initial.py`) bootstraps
the current month's partition plus the next two; `cti db ensure-partitions`
extends the window operationally.

## Schema versioning

Every persisted record carries `schema_version`. The plan is to land
upgraders in `cti/persistence/upgraders/` for any non-trivial migration so
the canonical store stays mixed-version readable. Don't widen the model
without also bumping `SCHEMA_VERSION` and shipping a tested upgrader.
