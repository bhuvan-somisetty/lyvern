"""FastAPI application: health endpoints and request-id middleware."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from lyvern import __version__
from lyvern.celery_app import check_redis
from lyvern.config import get_settings
from lyvern.db import check_db, get_engine
from lyvern.github.publisher import WriteGuard
from lyvern.github.webhook import verify_signature
from lyvern.logging import configure_logging, correlation_id
from lyvern.services.ingest import ingest_delivery
from lyvern.tasks import run_review
from lyvern_api.dashboard import router as dashboard_router

MAX_WEBHOOK_BYTES = 5_000_000


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.product_name, version=__version__)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = correlation_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers["x-request-id"] = rid
        return response

    app.include_router(dashboard_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        checks = {"database": check_db(), "redis": check_redis()}
        ok = all(checks.values())
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "not_ready", "checks": checks},
        )

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"name": settings.product_name, "version": __version__}

    @app.post("/webhooks/github")
    async def github_webhook(request: Request) -> JSONResponse:
        cfg = get_settings()
        secret = cfg.github_webhook_secret.get_secret_value() if cfg.github_webhook_secret else ""
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_WEBHOOK_BYTES:
            return JSONResponse(status_code=413, content={"status": "too_large"})
        body = await request.body()
        if len(body) > MAX_WEBHOOK_BYTES:
            return JSONResponse(status_code=413, content={"status": "too_large"})
        # The signature is checked over the raw bytes before anything is parsed.
        if not verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
            return JSONResponse(status_code=401, content={"status": "invalid_signature"})
        result = await run_in_threadpool(
            ingest_delivery,
            get_engine(),
            dict(request.headers),
            body,
            WriteGuard.from_setting(cfg.write_allowed_repos),
            lambda run_id: run_review.delay(str(run_id)),
        )
        content: dict[str, str] = {"status": result.status}
        if result.run_id is not None:
            content["run_id"] = str(result.run_id)
        return JSONResponse(status_code=result.http_status, content=content)

    return app


app = create_app()
