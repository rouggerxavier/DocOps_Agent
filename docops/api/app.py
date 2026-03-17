"""FastAPI application factory for DocOps Agent."""

from __future__ import annotations

import os
from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from docops.api.routes import (
    artifact,
    briefing,
    calendar,
    chat,
    compare,
    docs,
    flashcards,
    health,
    ingest,
    jobs,
    notes,
    studyplan,
    summarize,
    tasks,
)
from docops.api.routes import auth as auth_routes
from docops.auth.dependencies import get_current_user


def create_app() -> FastAPI:
    app = FastAPI(
        title="DocOps Agent API",
        description="RAG agent for local documents — PDF, MD, TXT",
        version="0.2.0",
        docs_url="/api/docs-ui",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS — allow frontend dev server and configurable origins
    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Criar tabelas no banco ao iniciar (idempotente)
    from docops.db.database import init_db
    init_db()

    # Dependencia de autenticacao aplicada a todas as rotas protegidas
    _auth = [Depends(get_current_user)]

    prefix = "/api"
    # Rotas publicas
    app.include_router(health.router, prefix=prefix, tags=["health"])
    app.include_router(auth_routes.router, prefix=prefix, tags=["auth"])

    # Rotas protegidas — exigem Bearer token
    app.include_router(docs.router, prefix=prefix, tags=["docs"], dependencies=_auth)
    app.include_router(ingest.router, prefix=prefix, tags=["ingest"], dependencies=_auth)
    app.include_router(chat.router, prefix=prefix, tags=["chat"], dependencies=_auth)
    app.include_router(summarize.router, prefix=prefix, tags=["summarize"], dependencies=_auth)
    app.include_router(compare.router, prefix=prefix, tags=["compare"], dependencies=_auth)
    app.include_router(artifact.router, prefix=prefix, tags=["artifacts"], dependencies=_auth)
    app.include_router(calendar.router, prefix=prefix, tags=["calendar"], dependencies=_auth)
    app.include_router(jobs.router, prefix=prefix, tags=["jobs"], dependencies=_auth)
    app.include_router(notes.router, prefix=prefix, tags=["notes"], dependencies=_auth)
    app.include_router(tasks.router, prefix=prefix, tags=["tasks"], dependencies=_auth)
    app.include_router(briefing.router, prefix=prefix, tags=["briefing"], dependencies=_auth)
    app.include_router(flashcards.router, prefix=prefix, tags=["flashcards"], dependencies=_auth)
    app.include_router(studyplan.router, prefix=prefix, tags=["studyplan"], dependencies=_auth)

    # ── Servir frontend React (web/dist/) ────────────────────────────────────
    # Resolve relativo à raiz do projeto (dois níveis acima de docops/api/)
    _frontend_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

    if _frontend_dist.exists():
        # Arquivos estáticos (JS, CSS, imagens gerados pelo Vite em /assets)
        _assets_dir = _frontend_dist / "assets"
        if _assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(_assets_dir)),
                name="assets",
            )

        # Catch-all: serve arquivos estáticos do dist/ ou index.html para SPA
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            # Tenta servir arquivo estático (ex: vite.svg, favicon.ico)
            file_path = (_frontend_dist / full_path).resolve()
            if full_path and file_path.is_file() and str(file_path).startswith(str(_frontend_dist)):
                return FileResponse(str(file_path))
            # Fallback: index.html para React Router
            return FileResponse(str(_frontend_dist / "index.html"))

    return app


app = create_app()
