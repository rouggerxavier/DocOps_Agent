"""FastAPI application factory for DocOps Agent."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from docops.api.routes import (
    artifact,
    briefing,
    capabilities,
    calendar,
    chat,
    compare,
    docs,
    flashcards,
    health,
    ingest,
    jobs,
    notes,
    pipeline,
    preferences,
    studyplan,
    summarize,
    tasks,
)
from docops.api.routes import auth as auth_routes
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.logging import get_logger
from docops.observability import (
    CORRELATION_ID_HEADER,
    CorrelationIdMiddleware,
    emit_event,
    get_request_correlation_id,
)

logger = get_logger("docops.api.app")


def _resolve_cors_settings() -> tuple[list[str], list[str], list[str], bool]:
    origins = list(config.cors_origins)
    if "*" in origins:
        if config.is_production:
            raise RuntimeError("CORS_ORIGINS nao pode conter '*' em producao.")
        origins = [origin for origin in origins if origin != "*"]

    if config.is_production and not origins:
        raise RuntimeError("CORS_ORIGINS deve ser uma allow list explicita em producao.")

    return (
        origins,
        config.cors_allow_methods,
        config.cors_allow_headers,
        config.cors_allow_credentials,
    )


def create_app() -> FastAPI:
    _in_prod = config.is_production
    app = FastAPI(
        title="DocOps Agent API",
        description="RAG agent for local documents - PDF, MD, TXT",
        version="0.2.0",
        docs_url=None if _in_prod else "/api/docs-ui",
        redoc_url=None if _in_prod else "/api/redoc",
        openapi_url=None if _in_prod else "/api/openapi.json",
    )

    # CORS allow list by environment.
    origins, allow_methods, allow_headers, allow_credentials = _resolve_cors_settings()

    # Correlation id and request lifecycle events.
    app.add_middleware(CorrelationIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )

    @app.exception_handler(Exception)
    async def _internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = get_request_correlation_id(request)
        emit_event(
            logger,
            "http.unhandled_exception",
            level="error",
            category="http",
            method=request.method,
            path=request.url.path,
            error_type=exc.__class__.__name__,
        )
        logger.exception("Unhandled API exception: %s", exc)
        return JSONResponse(
            status_code=500,
            headers={CORRELATION_ID_HEADER: correlation_id},
            content={
                "detail": "Internal server error",
                "correlation_id": correlation_id,
            },
        )

    # Create DB tables on startup (idempotent).
    from docops.db.database import init_db

    init_db()

    # Auth dependency for protected routes.
    _auth = [Depends(get_current_user)]

    prefix = "/api"
    # Public routes
    app.include_router(health.router, prefix=prefix, tags=["health"])
    app.include_router(auth_routes.router, prefix=prefix, tags=["auth"])

    # Protected routes - require Bearer token
    app.include_router(docs.router, prefix=prefix, tags=["docs"], dependencies=_auth)
    app.include_router(ingest.router, prefix=prefix, tags=["ingest"], dependencies=_auth)
    app.include_router(capabilities.router, prefix=prefix, tags=["capabilities"], dependencies=_auth)
    app.include_router(chat.router, prefix=prefix, tags=["chat"], dependencies=_auth)
    app.include_router(summarize.router, prefix=prefix, tags=["summarize"], dependencies=_auth)
    app.include_router(compare.router, prefix=prefix, tags=["compare"], dependencies=_auth)
    app.include_router(artifact.router, prefix=prefix, tags=["artifacts"], dependencies=_auth)
    app.include_router(calendar.router, prefix=prefix, tags=["calendar"], dependencies=_auth)
    app.include_router(jobs.router, prefix=prefix, tags=["jobs"], dependencies=_auth)
    app.include_router(notes.router, prefix=prefix, tags=["notes"], dependencies=_auth)
    app.include_router(tasks.router, prefix=prefix, tags=["tasks"], dependencies=_auth)
    app.include_router(preferences.router, prefix=prefix, tags=["preferences"], dependencies=_auth)
    app.include_router(briefing.router, prefix=prefix, tags=["briefing"], dependencies=_auth)
    app.include_router(flashcards.router, prefix=prefix, tags=["flashcards"], dependencies=_auth)
    app.include_router(studyplan.router, prefix=prefix, tags=["studyplan"], dependencies=_auth)
    app.include_router(pipeline.router, prefix=prefix, tags=["pipeline"], dependencies=_auth)

    # Serve React frontend (web/dist/)
    _frontend_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

    if _frontend_dist.exists():
        _assets_dir = _frontend_dist / "assets"
        if _assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(_assets_dir)),
                name="assets",
            )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            file_path = (_frontend_dist / full_path).resolve()
            if full_path and file_path.is_file() and str(file_path).startswith(str(_frontend_dist)):
                return FileResponse(str(file_path))
            return FileResponse(str(_frontend_dist / "index.html"))

    return app


app = create_app()
