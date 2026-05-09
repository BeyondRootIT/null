"""ASGI app: /healthz, /readyz, /metrics, /v1/* API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from cti.config.schema import get_settings
from cti.manager.registry import SourceRegistry
from cti.obs.auth import Principal, TokenStore
from cti.obs.metrics import REGISTRY
from cti.persistence.db import db_session
from cti.persistence.repositories import (
    DeadLetterRepo,
    FeedRunRepo,
    IndicatorLookupRepo,
    SourceRepo,
)


def _require(request: Request, scope: str) -> Principal:
    store: TokenStore = request.app.state.tokens
    principal = store.authenticate(request.headers.get("Authorization"))
    if principal is None or not principal.has(scope):
        raise _Unauthorized(scope)
    return principal


class _Unauthorized(Exception):
    def __init__(self, scope: str) -> None:
        self.scope = scope


async def _unauthorized_handler(request: Request, exc: _Unauthorized) -> Response:
    return JSONResponse(
        {"error": "unauthorized", "required_scope": exc.scope},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---- routes ---------------------------------------------------------------------


async def healthz(_: Request) -> Response:
    return PlainTextResponse("ok")


async def readyz(request: Request) -> Response:
    try:
        async with db_session() as session:
            await SourceRepo(session).list()
        return PlainTextResponse("ready")
    except Exception as exc:  # noqa: BLE001
        return PlainTextResponse(f"not ready: {exc}", status_code=503)


async def metrics(_: Request) -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


async def list_sources(request: Request) -> Response:
    _require(request, "read")
    registry: SourceRegistry = request.app.state.source_registry
    out: list[dict[str, Any]] = []
    async with db_session() as session:
        repo = SourceRepo(session)
        rows = {r.id: r for r in await repo.list()}
    for cfg in registry.all():
        row = rows.get(cfg.id)
        out.append(
            {
                "id": cfg.id,
                "name": cfg.name,
                "plugin": cfg.plugin,
                "enabled": cfg.enabled,
                "schedule": cfg.schedule,
                "watermark": (row.watermark if row else None) or {},
            }
        )
    return JSONResponse(out)


async def get_source(request: Request) -> Response:
    _require(request, "read")
    registry: SourceRegistry = request.app.state.source_registry
    try:
        cfg = registry.get(request.path_params["source_id"])
    except KeyError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(cfg.model_dump(mode="json"))


async def list_runs(request: Request) -> Response:
    _require(request, "read")
    source_id = request.query_params.get("source")
    limit = min(int(request.query_params.get("limit", "50")), 500)
    async with db_session() as session:
        rows = await FeedRunRepo(session).recent(source_id=source_id, limit=limit)
    return JSONResponse(
        [
            {
                "id": str(r.id),
                "source_id": r.source_id,
                "state": r.state,
                "started_at": r.started_at.isoformat(),
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "records_in": r.records_in,
                "records_out": r.records_out,
                "error": r.error,
                "raw_uri": r.raw_uri,
            }
            for r in rows
        ]
    )


async def get_run(request: Request) -> Response:
    _require(request, "read")
    run_id = UUID(request.path_params["run_id"])
    async with db_session() as session:
        row = await FeedRunRepo(session).get(run_id)
    if row is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(
        {
            "id": str(row.id),
            "source_id": row.source_id,
            "state": row.state,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "fetched_bytes": row.fetched_bytes,
            "records_in": row.records_in,
            "records_out": row.records_out,
            "error": row.error,
            "watermark": row.watermark,
            "raw_uri": row.raw_uri,
        }
    )


async def lookup_indicators(request: Request) -> Response:
    _require(request, "read")
    ind_type = request.query_params.get("type")
    value = request.query_params.get("value")
    limit = min(int(request.query_params.get("limit", "100")), 1000)
    async with db_session() as session:
        rows = await IndicatorLookupRepo(session).lookup(ind_type, value, limit)
    return JSONResponse(
        [
            {
                "id": str(r.id),
                "type": r.type,
                "value": r.value,
                "confidence": r.confidence,
                "tlp": r.tlp,
                "tags": r.tags,
                "first_seen_by_us": r.first_seen_by_us.isoformat(),
                "last_seen_by_us": r.last_seen_by_us.isoformat(),
            }
            for r in rows
        ]
    )


async def list_dlq(request: Request) -> Response:
    _require(request, "read")
    source_id = request.query_params.get("source")
    only_open = request.query_params.get("unreplayed", "true").lower() != "false"
    async with db_session() as session:
        rows = await DeadLetterRepo(session).list(source_id, only_open, limit=200)
    return JSONResponse(
        [
            {
                "id": r.id,
                "feed_run_id": str(r.feed_run_id),
                "source_id": r.source_id,
                "error_class": r.error_class,
                "error_msg": r.error_msg,
                "reason": r.reason,
                "created_at": r.created_at.isoformat(),
                "replayed_at": r.replayed_at.isoformat() if r.replayed_at else None,
            }
            for r in rows
        ]
    )


async def replay_dlq(request: Request) -> Response:
    _require(request, "trigger")
    dlq_id = int(request.path_params["dlq_id"])
    async with db_session() as session:
        await DeadLetterRepo(session).mark_replayed(dlq_id)
        await session.commit()
    return JSONResponse({"id": dlq_id, "replayed_at": datetime.now(UTC).isoformat()})


async def trigger_run(request: Request) -> Response:
    _require(request, "trigger")
    source_id = request.path_params["source_id"]
    registry: SourceRegistry = request.app.state.source_registry
    try:
        cfg = registry.get(source_id)
    except KeyError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    enqueuer = getattr(request.app.state, "enqueue", None)
    if enqueuer is None:
        return JSONResponse({"error": "queue_unavailable"}, status_code=503)
    job_id = await enqueuer(cfg.id)
    return JSONResponse({"queued": True, "source_id": cfg.id, "job_id": job_id})


def build_app(
    source_registry: SourceRegistry,
    *,
    tokens: TokenStore | None = None,
    enqueue: Any | None = None,
) -> Starlette:
    settings = get_settings()
    if tokens is None:
        tokens = TokenStore.load(settings.security.api_token_file)

    app = Starlette(
        debug=False,
        routes=[
            Route("/healthz", healthz),
            Route("/readyz", readyz),
            Route("/metrics", metrics),
            Route("/v1/sources", list_sources),
            Route("/v1/sources/{source_id}", get_source),
            Route("/v1/sources/{source_id}/trigger", trigger_run, methods=["POST"]),
            Route("/v1/runs", list_runs),
            Route("/v1/runs/{run_id}", get_run),
            Route("/v1/indicators", lookup_indicators),
            Route("/v1/dlq", list_dlq),
            Route("/v1/dlq/{dlq_id:int}/replay", replay_dlq, methods=["POST"]),
        ],
        exception_handlers={_Unauthorized: _unauthorized_handler},
    )
    app.state.source_registry = source_registry
    app.state.tokens = tokens
    app.state.enqueue = enqueue
    return app
