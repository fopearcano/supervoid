from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import prepare_database
from app.routers import ALL_ROUTERS, brain_gateway, brain_handoff, mcp, public_reader
from app.utils.logging import configure_logging, get_logger
from app.utils.middleware import REQUEST_ID_HEADER, RequestIdMiddleware

# Local-first demo media for the public reader (placeholder pages, posters).
PUBLIC_DEMO_DIR = Path(__file__).resolve().parent / "static" / "demo"

log = get_logger("app.main")


def _safe_db_url(url: str) -> str:
    """Mask the password component before logging a database URL."""
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    log.info(
        "%s starting · env=%s · db=%s",
        settings.app_name,
        settings.environment,
        _safe_db_url(settings.database_url),
    )
    mode = prepare_database()
    log.info("database ready · strategy=%s", mode)
    # Optional, best-effort prefix-cache prewarming for ACTIVE project prefixes
    # (Prompt 8). Default OFF and a no-op under dry_run, so dev/test boot is
    # unchanged. Fire-and-forget on a fresh session; never blocks startup.
    if settings.brain_prewarm_on_startup and settings.ai_provider != "dry_run":
        import asyncio

        async def _prewarm_on_startup() -> None:
            try:
                from sqlmodel import Session as _Session

                from app.db import engine as _engine
                from app.services import brain as _brain

                # prewarm_active is synchronous (it drives the provider via
                # asyncio.run), so run the whole DB+provider pass in a worker
                # thread — calling asyncio.run() from this running loop would
                # raise, and the session must not cross threads.
                def _run() -> dict:
                    with _Session(_engine) as s:
                        return _brain.session.prewarm_active(s)

                summary = await asyncio.to_thread(_run)
                log.info("brain prewarm complete · %s", summary)
            except Exception:
                log.exception("brain prewarm on startup failed")

        asyncio.create_task(_prewarm_on_startup())
    yield
    log.info("%s stopping", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Editorial management platform for publishing houses.",
        lifespan=lifespan,
    )

    # Order matters: CORS first so preflight requests don't trip the
    # request-id log, then the request-id middleware so every entry in
    # the access log carries a correlation id.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)

    for router_module in ALL_ROUTERS:
        app.include_router(router_module.router, prefix=settings.api_prefix)

    # Public Graphic Novel Webviewer — read-only, unauthenticated, and NOT
    # under the private /api prefix. Mounted at /public alongside its
    # local-first demo media (placeholder page images / posters).
    app.include_router(public_reader.router)
    if PUBLIC_DEMO_DIR.is_dir():
        app.mount(
            "/public/demo",
            StaticFiles(directory=PUBLIC_DEMO_DIR),
            name="public-demo",
        )

    # The Brain Gateway — an OpenAI-compatible surface for LibreChat. Mounted at
    # /brain (NOT under the private /api prefix); authenticated by a dedicated
    # Brain access token, never the browser JWT or the upstream vLLM key.
    app.include_router(brain_gateway.router)

    # The SUPERVOID MCP server — the governed tool layer for LibreChat (Model
    # Context Protocol, Streamable HTTP). Mounted at /mcp (NOT under /api);
    # authenticated by the internal service credential + signed user-context,
    # and every tool re-runs the policy service. Never exposes raw CRUD.
    app.include_router(mcp.router)

    # The Brain hand-off landing (Prompt 12) — root-mounted, token-authenticated.
    # A browser redirect from "Ask the Brain" lands at /brain-handoff, which
    # consumes the signed token and redirects to the LibreChat (Brain) UI.
    app.include_router(brain_handoff.router)

    # Every error response carries the same envelope: a human-readable
    # ``detail`` string plus the ``request_id`` (also on the header) so a
    # failure in the UI or a log line can be traced to one request.

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        # Preserve any exception-supplied headers (e.g. WWW-Authenticate on 401).
        headers = dict(getattr(exc, "headers", None) or {})
        headers[REQUEST_ID_HEADER] = rid
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": rid},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed.",
                "errors": jsonable_encoder(exc.errors()),
                "request_id": rid,
            },
            headers={REQUEST_ID_HEADER: rid},
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(
        request: Request, _exc: IntegrityError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        log.warning("integrity error · path=%s", request.url.path)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Database constraint violation.",
                "request_id": rid,
            },
            headers={REQUEST_ID_HEADER: rid},
        )

    @app.exception_handler(Exception)
    async def _internal_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # FastAPI's HTTPException is dispatched before this catch-all,
        # so anything reaching here is genuinely unexpected.
        rid = getattr(request.state, "request_id", "-")
        log.exception(
            "unhandled exception · path=%s · type=%s",
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error.",
                "request_id": rid,
            },
            headers={REQUEST_ID_HEADER: rid},
        )

    @app.get("/", tags=["root"], summary="Service identity")
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }

    return app


app = create_app()
