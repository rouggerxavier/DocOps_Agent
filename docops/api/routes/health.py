from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from docops.api.schemas import HealthResponse, ReadyResponse
from docops.config import config
from docops.db.database import SessionLocal

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


def _check_database() -> dict[str, object]:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "detail": "ok"}
    except Exception as exc:
        return {"ok": False, "detail": f"{exc.__class__.__name__}: {exc}"}
    finally:
        db.close()


def _check_directory(path: Path, *, writable: bool) -> dict[str, object]:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return {"ok": False, "detail": f"mkdir_failed: {exc.__class__.__name__}"}

    if writable:
        probe = path / f".ready-probe-{uuid4().hex}.tmp"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:
            return {"ok": False, "detail": f"write_failed: {exc.__class__.__name__}"}

    return {"ok": True, "detail": "ok"}


def _run_readiness_checks() -> tuple[bool, dict[str, dict[str, object]]]:
    checks: dict[str, dict[str, object]] = {
        "database": _check_database(),
        "uploads_dir": _check_directory(config.uploads_dir, writable=True),
        "artifacts_dir": _check_directory(config.artifacts_dir, writable=True),
        "chroma_dir": _check_directory(config.chroma_dir, writable=True),
    }
    is_ready = all(bool(item.get("ok")) for item in checks.values())
    return is_ready, checks


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse | JSONResponse:
    is_ready, checks = _run_readiness_checks()
    payload = {"status": "ok" if is_ready else "unready", "checks": checks}
    if is_ready:
        return ReadyResponse(**payload)
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
