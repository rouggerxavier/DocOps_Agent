"""Observability helpers for correlation ids and structured event envelopes."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

CORRELATION_ID_HEADER = "X-Correlation-ID"
STREAM_FALLBACK_HEADER = "X-DocOps-Stream-Fallback"
EVENT_SCHEMA_VERSION = 1

_CID_ALLOWED = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "docops_correlation_id",
    default="",
)


def new_correlation_id() -> str:
    """Generate a compact correlation id."""
    return uuid.uuid4().hex


def normalize_correlation_id(value: str | None) -> str:
    """Normalize incoming correlation id to a safe token."""
    raw = (value or "").strip()
    if raw and _CID_ALLOWED.fullmatch(raw):
        return raw
    return new_correlation_id()


def set_correlation_id(correlation_id: str) -> contextvars.Token[str]:
    """Set correlation id in contextvar and return reset token."""
    return _correlation_id_ctx.set(correlation_id)


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    """Reset correlation id context from a token."""
    _correlation_id_ctx.reset(token)


def get_correlation_id(default: str = "-") -> str:
    """Return active correlation id from context, fallback to default."""
    value = _correlation_id_ctx.get()
    return value or default


def get_request_correlation_id(request: Request | None, default: str = "-") -> str:
    """Get correlation id from request state or contextvar."""
    if request is not None:
        state_value = getattr(getattr(request, "state", None), "correlation_id", None)
        if isinstance(state_value, str) and state_value.strip():
            return state_value.strip()
    return get_correlation_id(default=default)


def is_stream_fallback_request(request: Request | None) -> bool:
    """Whether request is a stream->non-stream fallback call."""
    if request is None:
        return False
    return (request.headers.get(STREAM_FALLBACK_HEADER, "").strip() == "1")


def build_event_envelope(event: str, **fields: Any) -> dict[str, Any]:
    """Build canonical event envelope used by logs/ingestion pipelines."""
    envelope: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": get_correlation_id(),
    }
    for key, value in fields.items():
        if value is not None:
            envelope[key] = value
    return envelope


def emit_event(
    logger: logging.Logger,
    event: str,
    *,
    level: str = "info",
    **fields: Any,
) -> dict[str, Any]:
    """Emit normalized observability event as a single log line."""
    envelope = build_event_envelope(event, **fields)
    payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    log_fn = getattr(logger, level, logger.info)
    log_fn("DOCOPS_EVENT %s", payload)
    return envelope


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation id to request context and emit request lifecycle events."""

    def __init__(self, app):
        super().__init__(app)
        from docops.logging import get_logger

        self._logger = get_logger("docops.observability.http")

    async def dispatch(self, request: Request, call_next):
        correlation_id = normalize_correlation_id(request.headers.get(CORRELATION_ID_HEADER))
        token = set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        fallback_from_stream = is_stream_fallback_request(request)
        started_at = time.perf_counter()

        emit_event(
            self._logger,
            "http.request.started",
            category="http",
            method=request.method,
            path=request.url.path,
            query=(request.url.query or None),
            fallback_from_stream=fallback_from_stream,
            client_host=getattr(request.client, "host", None),
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            emit_event(
                self._logger,
                "http.request.failed",
                level="error",
                category="http",
                method=request.method,
                path=request.url.path,
                status_code=500,
                latency_ms=latency_ms,
                fallback_from_stream=fallback_from_stream,
                error_type=exc.__class__.__name__,
            )
            raise
        else:
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            emit_event(
                self._logger,
                "http.request.completed",
                category="http",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=latency_ms,
                fallback_from_stream=fallback_from_stream,
            )
            return response
        finally:
            reset_correlation_id(token)
