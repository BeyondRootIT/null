# Troubleshooting

## "no plugin <name> in group <group>"

`PluginLoadError`. The connector / parser / enricher / publisher you named in
`sources.yaml` isn't installed.

```bash
cti plugins                  # list discovered entry points
pip show cti                 # confirm the package itself is installed
pip install -e .             # re-install if you added a new entry point
```

## "validation error" at startup

`pydantic.ValidationError` from `SourceConfig` or one of the plugin config
models. The error message points at the offending field. Run
`cti validate-config` to see all errors at once.

## A feed succeeds but produces 0 records

Check `cti show-effective-config <id>`. Common causes:

| Symptom | Cause | Fix |
| --- | --- | --- |
| `records_in > 0` but `records_out = 0` | Allowlist enricher dropped everything | Inspect `cti_dropped_total{reason="enricher"}`; relax `enricher_params.allowlist`. |
| `parse_errors > 0` and `records_in = 0` | Parser config doesn't match the feed | Run `cti run-once <id>` with `CTI_OBS_LOG_LEVEL=DEBUG`. |
| Steady 304 from upstream | Conditional GET hit; no new content | Expected. Run `cti backfill --since ...` to force a full pull. |

## `EgressBlocked` errors

The SSRF guard refused a URL. Possible reasons:

- The URL resolved to a private / loopback / metadata IP.
- The URL is `http://...` but the source didn't set `params.allow_http: true`.

If the upstream is genuinely on a private network (you're running
internally), set `params.allow_http: true` and add the host to your egress
allowlist. **Don't** disable the guard globally.

## Circuit is `OPEN` for source X

A source has hit `circuit.failure_threshold` consecutive failures. Causes:

- Upstream down → wait for `circuit.recovery_seconds`.
- Auth credential expired → check `cti dlq list --source X`.
- Egress blocked → see above.

The breaker auto-transitions to `half_open` after `recovery_seconds` and
resets to `closed` on the next success.

## `cti db migrate` fails

- "schema cti already exists" — that's fine; `IF NOT EXISTS` handles it.
- "permission denied" — your DB user lacks `CREATE EXTENSION` (we install
  `pgcrypto` and `pg_trgm`). Either grant superuser briefly or pre-create
  the extensions manually.
- "could not connect" — `CTI_DB_DSN` is wrong or Postgres isn't ready;
  the compose file uses healthchecks to gate `migrate` on `postgres`.

## Worker crashes with `BaseExceptionGroup`

The pipeline runs all stages in a `TaskGroup`. If a stage raises, the group
re-raises a `BaseExceptionGroup`. `cti.core.pipeline.run_with_outcome`
flattens this into a `RunResult`; if you see it bubbling up, the *outermost*
caller is unprotected — that's a bug, please report.

## Tests fail with "Postgres container failed to start"

Integration tests use `testcontainers[postgres]` and need Docker available.
On a host without Docker, run only unit + contract:

```bash
uv run pytest tests/unit tests/contract
```

## Common log key conventions

| Key | Meaning |
| --- | --- |
| `run_id` | UUID of the current `feed_runs` row. |
| `source_id` | Source identifier from `sources.yaml`. |
| `event` | Short snake_case action name. |
| `state` | `RunState` value at the moment of the log. |
| `error` | `str(exception)` truncated. |

Use these to filter quickly in your log backend.
