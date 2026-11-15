"""FastAPI application: health endpoints and request-id middleware."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from lyvern import __version__
from lyvern.celery_app import check_redis
from lyvern.config import get_settings
from lyvern.db import check_db
from lyvern.logging import configure_logging, correlation_id


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

    return app


app = create_app()
