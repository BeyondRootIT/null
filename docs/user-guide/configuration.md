# Configuration

Three layers, evaluated in order:

1. **`config/defaults.yaml`** — framework-wide defaults (rate limit, retry, …).
2. **`config/sources.yaml`** — per-source configuration; required.
3. **Environment variables** — runtime infrastructure (DB, Redis, archive, obs).

## Environment variables

All env vars are read by `cti.config.schema.Settings` (Pydantic Settings).

### Database

| Var | Default | Notes |
| --- | --- | --- |
| `CTI_DB_DSN` | `postgresql+asyncpg://cti_user:cti_pass@postgres:5432/cti` | asyncpg driver. |
| `CTI_DB_POOL_SIZE` | `5` | |
| `CTI_DB_MAX_OVERFLOW` | `10` | |

### Redis

| Var | Default | Notes |
| --- | --- | --- |
| `CTI_REDIS_URL` | `redis://redis:6379/0` | Used by arq + rate limits. |

### Archive

| Var | Default | Notes |
| --- | --- | --- |
| `CTI_ARCHIVE_BACKEND` | `filesystem` | `filesystem` or `s3`. |
| `CTI_ARCHIVE_ROOT` | `/var/lib/cti/raw` | filesystem only. |
| `CTI_ARCHIVE_BUCKET` | unset | s3 only. |
| `CTI_ARCHIVE_PREFIX` | `raw` | s3 only. |
| `CTI_ARCHIVE_ENDPOINT_URL` | unset | s3 only; for MinIO. |

### Observability

| Var | Default |
| --- | --- |
| `CTI_OBS_LOG_LEVEL` | `INFO` |
| `CTI_OBS_LOG_JSON` | `true` |
| `CTI_OBS_API_PORT` | `8080` |
| `CTI_OBS_METRICS_PORT` | `9090` |
| `CTI_OBS_OTEL_ENDPOINT` | unset (OTel disabled) |
| `CTI_OBS_SERVICE_NAME` | `cti` |

### Security

| Var | Default | Notes |
| --- | --- | --- |
| `CTI_SEC_API_TOKEN_FILE` | unset | Path to `api_tokens.yaml`; if unset, API has zero valid tokens. |
| `CTI_SEC_ALLOW_HTTP_EGRESS` | `false` | Process-wide override; per-source `allow_http: true` is preferred. |

### Runtime

| Var | Default |
| --- | --- |
| `CTI_RUN_SOURCES_FILE` | `config/sources.yaml` |
| `CTI_RUN_GLOBAL_CONCURRENCY` | `50` |
| `CTI_RUN_DEFAULT_RPS` | `5.0` |
| `CTI_RUN_ARQ_QUEUE` | `cti:queue` |

## `sources.yaml`

Top-level shape:

```yaml
sources:
  - id: my_source              # required, unique, alnum + _ -
    name: "Friendly name"
    plugin: http_csv           # connector entry-point name
    parser: csv                # parser entry-point name
    enrichers: [defang, allowlist]
    publishers: [postgres]     # postgres is always added
    schedule: "*/15 * * * *"   # cron, 5-field
    jitter_seconds: 60         # +/- random delay before enqueue
    rate_limit_rps: 1.0        # per-host ceiling
    max_parallelism: 1         # MaxInstances per source
    timeout_seconds: 60
    retry:
      max_attempts: 5
      initial_seconds: 1.0
      max_seconds: 60.0
      jitter_seconds: 1.0
    circuit:
      failure_threshold: 5
      recovery_seconds: 300.0
    tlp: GREEN
    severity_default: info
    confidence_default: 80
    tags: ["my", "source"]
    params: { url: "https://feed.example.com/file.csv" }   # connector params
    parser_params: { has_header: true }                    # parser params
    enricher_params:
      allowlist:
        drop_private_ips: true
    publisher_params: {}
    normalize:
      indicator_type: url        # OR type_field: "type" for per-record
      value_field: url
      tags_field: tags
      static_tags: ["my"]
      tlp_default: GREEN
      confidence_default: 80
```

## Plugin parameters

Each plugin declares a Pydantic config model; the manager validates
`params` / `parser_params` / `enricher_params[name]` / `publisher_params[name]`
against it at startup. **Misconfig fails fast with a clear error.**

See [`technical/plugin-sdk.md`](../technical/plugin-sdk.md) for plugin-specific
schemas, and [`tutorials/02-add-a-source.md`](../tutorials/02-add-a-source.md)
for a walkthrough.

## Secrets

Refs inside `sources.yaml` are resolved at load time:

```yaml
params:
  auth_bearer: "${env:URLHAUS_API_KEY}"
  password: "${file:/run/secrets/feed-x-password}"
```

`${env:VAR}` reads the environment (empty string if unset). `${file:/path}`
reads + trims a file (empty string if missing). Don't put plaintext secrets
in `sources.yaml`.

## API tokens

`secrets/api_tokens.yaml`, pointed to by `CTI_SEC_API_TOKEN_FILE`:

```yaml
tokens:
  - token: "<long-random-string>"
    name: "operator-readonly"
    scopes: ["read"]
  - token: "<another-long-random-string>"
    name: "operator-trigger"
    scopes: ["read", "trigger"]
```

Reload by restarting the API process. Rotate by editing the file.

## Inspecting effective config

```bash
cti show-effective-config <source_id>   # Pydantic-resolved, secrets masked
cti show-config                          # framework Settings, secrets masked
cti validate-config                      # exits 0 / non-zero
```
