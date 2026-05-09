# Security

## Egress (SSRF)

`cti.security.egress.check_url()` resolves the URL's hostname and refuses any
RFC1918 / loopback / link-local / cloud-metadata IP, plus a few extras:

```
0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16,
172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.168.0.0/16,
198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24,
224.0.0.0/4, 240.0.0.0/4, ::1/128, fc00::/7, fe80::/10
```

Plain HTTP is **rejected by default**; opt in per-source via
`params.allow_http: true`. `EgressBlocked` is a `PermanentError`, so blocked
URLs go to `dead_letters`, not retry.

The HTTP connector base (`HttpConnectorBase`) calls `check_url` at the top of
`fetch()` — every shipped HTTP plugin inherits it.

## TLP

TLP v2.0 (`CLEAR`, `GREEN`, `AMBER`, `AMBER+STRICT`, `RED`) is stored
**per-observation**, never aggregated to a single canonical value on
`indicators`. `cti.security.tlp.tlp_max(...)` returns the strictest of N
values for use at publish time:

```python
from cti.security.tlp import tlp_max, TLP

tlp_max(TLP.GREEN, TLP.AMBER, TLP.CLEAR) == TLP.AMBER
tlp_max(TLP.AMBER_STRICT, TLP.RED) == TLP.RED
```

Publishers (`webhook`, `kafka`) declare a `max_tlp` they're willing to emit.
Records exceeding that bar are dropped *for that publisher only* and counted
under `cti_dropped_total{reason="tlp:<publisher>"}`. The Postgres canonical
sink stores everything regardless — TLP filtering is a **read-side** concern.

## Secrets

`sources.yaml` resolves two secret reference types via
`cti.config.secrets.resolve_secrets`:

| Form | Resolves to |
| --- | --- |
| `${env:VAR}` | Value of environment variable `VAR`, or empty string. |
| `${file:/path}` | Trimmed contents of `/path`, or empty string if missing. |

Inline secrets in YAML are not blocked, but discouraged. Use
`/run/secrets/...` mounts (Docker secrets) or env vars.

The HTTP API uses **static bearer tokens** loaded from
`${CTI_SEC_API_TOKEN_FILE}` (default: not set). See
[`api-reference.md`](../user-guide/api-reference.md) for the format. Tokens
are scoped:

| Scope | Grants |
| --- | --- |
| `read` | All `GET /v1/...`. |
| `trigger` | `POST /v1/sources/{id}/trigger`, `POST /v1/dlq/{id}/replay`. |
| `admin` | Implies all scopes. |

There is **no anonymous access** to `/v1/*`. Rotate tokens by editing the
file and reloading the API process.

## Plugin sandboxing (roadmap)

v0 ships **no** sandboxing — plugins run in-process. The plan is:

1. **v0.x**: each plugin declares a permissions manifest in its
   `pyproject.toml` (`allowed_hosts`, `allowed_env`, `requires_network`).
   The egress guard enforces `allowed_hosts`; env scrubbing enforces
   `allowed_env`. Refusal is a `PluginConfigError`.
2. **v0.6**: out-of-process plugin transport (subprocess + JSONL stdin/stdout,
   LSP-style). The ABCs are designed to be message-passable, so this is a
   transport swap, not a redesign.

Until then, treat third-party plugins as **trusted code** and review them
before installing.

## Migrations and zero-downtime deploys

`cti db migrate` runs `alembic upgrade head` and is **never** auto-invoked at
process startup. Discipline:

- Use **expand-then-contract**: add nullable column → backfill → switch reads → drop old.
- Avoid single-step destructive migrations (DROP COLUMN, ALTER TYPE NOT NULL)
  — they break rolling deploys.
- A CI rejection rule for risky migration patterns is on the v0.x roadmap.
