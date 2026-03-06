"""Engine, sessão e Base declarativa do SQLAlchemy."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from docops.config import config


def _make_engine():
    url = config.database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


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
