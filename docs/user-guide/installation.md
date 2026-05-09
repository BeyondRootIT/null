# Installation

## Local development

Requires Python 3.12+ and `uv` (or any PEP 621 installer).

```bash
git clone <repo> cti && cd cti
uv sync --extra dev          # creates .venv with framework + dev tools
cp config/sources.example.yaml config/sources.yaml
cp secrets/api_tokens.example.yaml secrets/api_tokens.yaml   # for the HTTP API
```

You'll also need a Postgres + Redis to run end-to-end. The simplest path is
docker compose; for unit tests alone, no infra is required:

```bash
uv run pytest tests/unit tests/contract
```

## Docker Compose

The shipped `docker-compose.yml` defines the full stack: Postgres, Redis,
migrate (one-shot), 2× workers, scheduler, API.

```bash
docker compose --profile obs up -d   # plus Prometheus + Grafana
docker compose run --rm migrate       # alembic upgrade head
docker compose exec app-worker cti plugins
docker compose exec app-worker cti run-once abuse_ch_urlhaus
```

Profiles:

| Profile | Adds |
| --- | --- |
| `obs` | Prometheus (`:9090`), Grafana (`:3000`). |
| `s3` | MinIO (`:9001` console, `:9100` API). |
| `kafka` | Kafka (`:9092`). |

## Production / Kubernetes (sketch)

The Dockerfile is multi-stage, non-root, and uses `tini` as PID 1. Roughly:

```
Deployment   cti-scheduler   replicas: 1   command: ["cti", "scheduler"]
Deployment   cti-worker      replicas: N   command: ["cti", "worker"]
Deployment   cti-api         replicas: 2   command: ["cti", "api", "--host", "0.0.0.0"]
Job          cti-migrate     command: ["cti", "db", "migrate"]
CronJob      cti-partitions  command: ["cti", "db", "ensure-partitions", "--months", "3"]
```

Helm chart is on the v1.0 roadmap.

## Verifying the install

```bash
cti plugins                            # lists all 13 entry points
CTI_RUN_SOURCES_FILE=config/sources.yaml cti validate-config   # OK: N sources
cti show-config                        # resolved settings, secrets masked
```

If `cti` isn't on your PATH, use `uv run cti …` or `python -m cti …`.
