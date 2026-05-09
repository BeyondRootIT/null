# HTTP API reference

The API is exposed by `cti api` (Starlette + Uvicorn) on `:8080` by default,
serving alongside `/healthz`, `/readyz`, `/metrics`.

## Authentication

All `/v1/*` endpoints require a `Bearer` token. Tokens live in the file pointed
to by `CTI_SEC_API_TOKEN_FILE` (see [configuration](./configuration.md#api-tokens)).
There is **no anonymous access**. Scopes:

| Scope | Required for |
| --- | --- |
| `read` | Every `GET /v1/...`. |
| `trigger` | `POST /v1/sources/{id}/trigger`, `POST /v1/dlq/{id}/replay`. |
| `admin` | Implies all scopes. |

Failed auth returns `401` with `WWW-Authenticate: Bearer` and a JSON body
`{"error": "unauthorized", "required_scope": "<scope>"}`.

## Health

```
GET  /healthz           200 "ok"               (always, while process up)
GET  /readyz            200 "ready" | 503      (DB session check)
GET  /metrics           200 prometheus text
```

## v1 endpoints

### Sources

```
GET /v1/sources
GET /v1/sources/{source_id}
POST /v1/sources/{source_id}/trigger              [scope: trigger]
```

`GET /v1/sources` returns a list of `{id, name, plugin, enabled, schedule, watermark}`.

`POST .../trigger` enqueues a `run_feed(source_id)` arq job and returns
`{queued: true, source_id, job_id}`. The actual run happens on a worker —
poll `/v1/runs?source=...` to follow it.

### Runs

```
GET /v1/runs?source={id}&limit={n}     # default limit 50, max 500
GET /v1/runs/{run_id}
```

Each run row includes `state` (`PENDING|RUNNING|SUCCESS|PARTIAL|FAILED`),
counts, watermark, and `raw_uri` for replay.

### Indicators

```
GET /v1/indicators?type={ipv4|domain|url|...}&value={...}&limit={n}
```

Single-row lookup or paginated list. No fuzzy matching in v0 (planned: GIN
trigram on value at v0.1).

### Dead letters

```
GET  /v1/dlq?source={id}&unreplayed={true|false}      # default unreplayed=true
POST /v1/dlq/{dlq_id}/replay                          [scope: trigger]
```

`POST .../replay` only marks the row replayed in v0; actual re-execution lands
in v0.1.

## Errors

| Code | Body | Cause |
| --- | --- | --- |
| `401` | `{"error":"unauthorized","required_scope":"..."}` | Missing/invalid token or insufficient scope. |
| `404` | `{"error":"not_found"}` | Unknown source / run / dlq id. |
| `503` | `{"error":"queue_unavailable"}` | API was started without an arq enqueuer (read-only mode). |

## Versioning

The API is versioned at the path (`/v1/...`). Backwards-incompatible changes
will land as `/v2/...` rather than mutating `/v1/...`. Field additions
(non-removing) are allowed inside `/v1/...`.

## Example

```bash
TOKEN=...
curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/v1/sources

curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/v1/sources/abuse_ch_urlhaus/trigger

curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/v1/indicators?type=url&value=http://malicious.example.com/a"
```
