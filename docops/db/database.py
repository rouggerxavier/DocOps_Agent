"""Engine, sessão e Base declarativa do SQLAlchemy."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from docops.config import config


def _make_engine():
    url = config.database_url
    kwargs = {}
    if url.startswith("sqlite"):
        # CI and fresh environments may not have the DB parent dir yet.
        # Ensure SQLite file path can be opened before creating the engine.
        try:
            from sqlalchemy.engine.url import make_url

            parsed = make_url(url)
            db_path = parsed.database
            if db_path and db_path != ":memory:":
                Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback: keep behavior unchanged if URL parsing fails.
            pass
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope(bind: Any | None = None) -> Iterator[Session]:
    """Open/close a SQLAlchemy session, optionally bound to a specific engine/bind.

    Useful for thread workers that must not reuse request-scoped sessions.
    """
    SessionFactory = (
        SessionLocal
        if bind is None
        else sessionmaker(autocommit=False, autoflush=False, bind=bind)
    )
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """Dependency FastAPI: abre e fecha sessão por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria todas as tabelas se não existirem (idempotente)."""
    from docops.db import models  # noqa: F401 — importar para registrar modelos na Base
    Base.metadata.create_all(bind=engine)
