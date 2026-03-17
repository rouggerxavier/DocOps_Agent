"""FastAPI application factory for DocOps Agent."""

from __future__ import annotations

import os
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    return app


app = create_app()
