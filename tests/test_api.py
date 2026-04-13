"""Smoke tests da API — com suporte a auth."""

from __future__ import annotations

import os
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock, patch

# Setar vars antes de qualquer import da app
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from docops.api.app import app
from docops.auth.dependencies import get_current_user
from docops.db.database import Base, get_db
from docops.db.models import User, UserPreferenceRecord


# ── Banco de dados em memória para testes ─────────────────────────────────────

_TEST_DB_URL = "sqlite:///:memory:"
_test_engine = create_engine(
    _TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def _override_get_db():
    Base.metadata.create_all(bind=_test_engine)
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

# Cliente sem autenticação
client = TestClient(app)


def _make_auth_client():
    """Retorna um TestClient com usuário fake autenticado via dependency override."""
    fake_user = User(id=1, name="Tester", email="tester@example.com",
                     password_hash="x", is_active=True)

    def _fake_auth():
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_auth
    return TestClient(app), fake_user


def _make_auth_client_for_user(user_id: int):
    fake_user = User(
        id=int(user_id),
        name=f"Tester {int(user_id)}",
        email=f"tester{int(user_id)}@example.com",
        password_hash="x",
        is_active=True,
    )

    def _fake_auth():
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_auth
    return TestClient(app), fake_user


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)


# ── Health (público) ──────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_ok():
    checks = {
        "database": {"ok": True, "detail": "ok"},
        "uploads_dir": {"ok": True, "detail": "ok"},
        "artifacts_dir": {"ok": True, "detail": "ok"},
        "chroma_dir": {"ok": True, "detail": "ok"},
    }
    with patch("docops.api.routes.health._run_readiness_checks", return_value=(True, checks)):
        resp = client.get("/api/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True


def test_ready_returns_503_when_dependency_fails():
    checks = {
        "database": {"ok": False, "detail": "OperationalError"},
        "uploads_dir": {"ok": True, "detail": "ok"},
        "artifacts_dir": {"ok": True, "detail": "ok"},
        "chroma_dir": {"ok": True, "detail": "ok"},
    }
    with patch("docops.api.routes.health._run_readiness_checks", return_value=(False, checks)):
        resp = client.get("/api/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unready"
    assert body["checks"]["database"]["ok"] is False


# ── Auth: register ────────────────────────────────────────────────────────────

def test_register_ok():
    Base.metadata.create_all(bind=_test_engine)
    resp = client.post("/api/auth/register", json={
        "name": "Alice",
        "email": "alice@example.com",
        "password": "senha1234",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["name"] == "Alice"
    assert "id" in data


def test_register_duplicate_email():
    Base.metadata.create_all(bind=_test_engine)
    payload = {"name": "Bob", "email": "bob_dup@example.com", "password": "senha1234"}
    client.post("/api/auth/register", json=payload)
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


def test_register_short_password():
    resp = client.post("/api/auth/register", json={
        "name": "Carol", "email": "carol@example.com", "password": "abc"
    })
    assert resp.status_code == 422  # validação Pydantic


# ── Auth: login ───────────────────────────────────────────────────────────────

def test_login_ok():
    Base.metadata.create_all(bind=_test_engine)
    client.post("/api/auth/register", json={
        "name": "Dave", "email": "dave@example.com", "password": "senha1234"
    })
    resp = client.post("/api/auth/login", json={
        "email": "dave@example.com", "password": "senha1234"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid():
    resp = client.post("/api/auth/login", json={
        "email": "naoexiste@example.com", "password": "qualquer"
    })
    assert resp.status_code == 401


# ── Auth: me ──────────────────────────────────────────────────────────────────

def test_me_sem_token():
    # Sem token deve negar acesso
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_com_token():
    Base.metadata.create_all(bind=_test_engine)
    client.post("/api/auth/register", json={
        "name": "Eve", "email": "eve@example.com", "password": "senha1234"
    })
    login_resp = client.post("/api/auth/login", json={
        "email": "eve@example.com", "password": "senha1234"
    })
    token = login_resp.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "eve@example.com"


# ── Rotas protegidas retornam 403 sem token ───────────────────────────────────

def test_docs_sem_token():
    _clear_auth_override()
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_chat_sem_token():
    _clear_auth_override()
    resp = client.post("/api/chat", json={"message": "oi"})
    assert resp.status_code == 401


def test_capabilities_sem_token():
    _clear_auth_override()
    resp = client.get("/api/capabilities")
    assert resp.status_code == 401


# ── Testes existentes com autenticação via override ───────────────────────────

def test_docs_empty(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setattr("docops.api.routes.docs.tool_list_docs", lambda: [])
    resp = auth_client.get("/api/docs")
    assert resp.status_code == 200
    assert resp.json() == []
    _clear_auth_override()


def test_docs_with_data(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setattr(
        "docops.api.routes.docs.tool_list_docs",
        lambda: [{"file_name": "manual.pdf", "source": "/docs/manual.pdf", "chunk_count": 12}],
    )
    resp = auth_client.get("/api/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["file_name"] == "manual.pdf"
    assert data[0]["chunk_count"] == 12
    _clear_auth_override()


def test_chat_missing_api_key(monkeypatch):
    auth_client, _ = _make_auth_client()

    def raise_env(*a, **kw):
        raise EnvironmentError("Required environment variable 'GEMINI_API_KEY' is not set.")

    monkeypatch.setattr("docops.api.routes.chat._run_chat", raise_env)
    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 503
    _clear_auth_override()


def test_chat_success(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Test answer [Fonte 1]",
        "sources_section": "**Fontes:**\n- [Fonte 1] manual.pdf",
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="some chunk text",
                metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "abc"},
            )
        ],
    }
    monkeypatch.setattr("docops.api.routes.chat._run_chat", lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state)
    resp = auth_client.post("/api/chat", json={"message": "hello", "session_id": "s1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Test answer [Fonte 1]"
    assert data["intent"] == "qa"
    assert len(data["sources"]) == 1
    assert data["sources"][0]["file_name"] == "manual.pdf"
    assert data["session_id"] == "s1"
    assert data["quality_signal"] is not None
    assert data["quality_signal"]["level"] in {"high", "medium", "low"}
    assert "score" in data["quality_signal"]
    _clear_auth_override()


def test_chat_response_has_correlation_id_header(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: {
            "answer": "ok",
            "intent": "qa",
            "retrieved_chunks": [],
        },
    )

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    correlation_id = resp.headers.get("x-correlation-id")
    assert correlation_id is not None
    assert len(correlation_id) >= 8
    _clear_auth_override()


def test_chat_propagates_correlation_id_to_worker_thread(monkeypatch):
    auth_client, _ = _make_auth_client()
    expected_cid = "tracecid-12345678"

    def _fake_run(_msg, _top_k, user_id=0, doc_names=None, strict_grounding=False):
        from docops.observability import get_correlation_id

        return {
            "answer": f"cid={get_correlation_id()}",
            "intent": "qa",
            "retrieved_chunks": [],
        }

    monkeypatch.setattr("docops.api.routes.chat._run_chat", _fake_run)
    monkeypatch.setattr(
        "docops.api.routes.chat._apply_low_confidence_guardrail",
        lambda answer, quality_signal: (answer, False),
    )

    resp = auth_client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"X-Correlation-ID": expected_cid},
    )
    assert resp.status_code == 200
    assert resp.json()["answer"] == f"cid={expected_cid}"
    assert resp.headers.get("x-correlation-id") == expected_cid
    _clear_auth_override()


def test_chat_stream_success(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Test answer [Fonte 1]",
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="some chunk text",
                metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "abc"},
            )
        ],
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat/stream", json={"message": "hello", "session_id": "s1"})
    assert resp.status_code == 200
    assert "text/event-stream" in (resp.headers.get("content-type") or "")

    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events
    assert events[0]["type"] == "start"

    deltas = "".join(event.get("delta", "") for event in events if event.get("type") == "delta")
    final_event = next(event for event in events if event.get("type") == "final")
    assert deltas == "Test answer [Fonte 1]"
    assert final_event["response"]["answer"] == "Test answer [Fonte 1]"
    assert final_event["response"]["session_id"] == "s1"
    _clear_auth_override()


def test_chat_stream_has_single_final_and_single_terminal_in_repeated_runs(monkeypatch):
    from docops.api.contracts import validate_chat_stream_sequence

    auth_client, _ = _make_auth_client()
    fake_state = {"answer": "ok", "intent": "qa", "retrieved_chunks": []}
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    for idx in range(10):
        resp = auth_client.post(
            "/api/chat/stream",
            json={"message": f"hello {idx}", "session_id": f"s-{idx}"},
        )
        assert resp.status_code == 200

        events = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ")
        ]
        errors = validate_chat_stream_sequence(events)
        assert not errors, f"invalid stream sequence on run {idx}: {errors}"

        final_count = sum(1 for event in events if event.get("type") == "final")
        terminal_count = sum(1 for event in events if event.get("type") in {"done", "error"})
        assert final_count == 1
        assert terminal_count == 1
        assert events[-1]["type"] == "done"

    _clear_auth_override()


def test_chat_stream_status_progression(monkeypatch):
    auth_client, _ = _make_auth_client()
    fake_state = {"answer": "ok", "intent": "qa", "retrieved_chunks": []}
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat/stream", json={"message": "hello", "session_id": "s1"})
    assert resp.status_code == 200

    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    status_events = [event for event in events if event.get("type") == "status"]
    stages = [str(event.get("stage", "")) for event in status_events]
    assert stages, "expected status events in stream"

    required = ["analyzing", "retrieving", "drafting", "finalizing"]
    positions = [stages.index(stage) for stage in required]
    assert positions == sorted(positions)
    _clear_auth_override()


def test_chat_stream_events_include_correlation_id(monkeypatch):
    auth_client, _ = _make_auth_client()
    expected_cid = "streamcid-12345678"
    fake_state = {"answer": "ok", "intent": "qa", "retrieved_chunks": []}
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post(
        "/api/chat/stream",
        json={"message": "hello", "session_id": "s1"},
        headers={"X-Correlation-ID": expected_cid},
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-correlation-id") == expected_cid

    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events
    assert all(event.get("correlation_id") == expected_cid for event in events)
    _clear_auth_override()


def test_chat_stream_emits_error_event_on_environment_error(monkeypatch):
    auth_client, _ = _make_auth_client()

    def raise_env(*a, **kw):
        raise EnvironmentError("Required environment variable 'GEMINI_API_KEY' is not set.")

    monkeypatch.setattr("docops.api.routes.chat._run_chat", raise_env)
    resp = auth_client.post("/api/chat/stream", json={"message": "hello"})
    assert resp.status_code == 200

    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    error_event = next(event for event in events if event.get("type") == "error")
    assert error_event["status_code"] == 503
    assert "GEMINI_API_KEY" in error_event["detail"]
    _clear_auth_override()


def test_chat_stream_emits_timeout_error_event(monkeypatch):
    auth_client, _ = _make_auth_client()

    async def _raise_timeout(*_args, **_kwargs):
        raise TimeoutError("model timed out")

    monkeypatch.setattr("docops.api.routes.chat._build_chat_response", _raise_timeout)
    resp = auth_client.post("/api/chat/stream", json={"message": "hello"})
    assert resp.status_code == 200

    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    error_event = next(event for event in events if event.get("type") == "error")
    assert error_event["status_code"] == 504
    assert "timed out" in error_event["detail"].lower()
    assert events[-1]["type"] == "error"
    _clear_auth_override()


def test_chat_stream_handles_many_small_chunks_without_breaking_sequence(monkeypatch):
    from docops.api.contracts import validate_chat_stream_sequence

    auth_client, _ = _make_auth_client()
    answer = "0123456789" * 25
    fake_state = {"answer": answer, "intent": "qa", "retrieved_chunks": []}

    monkeypatch.setattr("docops.api.routes.chat._STREAM_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )
    monkeypatch.setattr(
        "docops.api.routes.chat._apply_low_confidence_guardrail",
        lambda answer, quality_signal: (answer, False),
    )

    resp = auth_client.post("/api/chat/stream", json={"message": "hello", "session_id": "s-jitter"})
    assert resp.status_code == 200

    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    errors = validate_chat_stream_sequence(events)
    assert not errors, f"invalid stream sequence under many chunks: {errors}"

    delta_chunks = [event.get("delta", "") for event in events if event.get("type") == "delta"]
    assert len(delta_chunks) >= 50
    assert "".join(delta_chunks) == answer
    _clear_auth_override()


def test_capabilities_returns_feature_flags():
    auth_client, _ = _make_auth_client()
    resp = auth_client.get("/api/capabilities")
    assert resp.status_code == 200
    payload = resp.json()
    assert "map" in payload
    assert payload["map"]["chat_streaming_enabled"] is True
    assert payload["map"]["strict_grounding_enabled"] is True
    assert "flags" in payload and len(payload["flags"]) >= 3
    _clear_auth_override()


def test_preferences_endpoint_requires_feature_flag(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.delenv("FEATURE_PERSONALIZATION_ENABLED", raising=False)

    resp = auth_client.get("/api/preferences")
    assert resp.status_code == 503
    assert "disabled" in str(resp.json().get("detail", "")).lower()
    _clear_auth_override()


def test_preferences_endpoints_require_auth_for_read_write_delete(monkeypatch):
    monkeypatch.setenv("FEATURE_PERSONALIZATION_ENABLED", "true")
    _clear_auth_override()

    get_resp = client.get("/api/preferences")
    assert get_resp.status_code == 401

    put_resp = client.put("/api/preferences", json={"tone": "objective"})
    assert put_resp.status_code == 401

    reset_resp = client.post("/api/preferences/reset")
    assert reset_resp.status_code == 401

    delete_resp = client.delete("/api/preferences")
    assert delete_resp.status_code == 401


def test_preferences_get_returns_defaults_and_persists(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("FEATURE_PERSONALIZATION_ENABLED", "true")
    Base.metadata.create_all(bind=_test_engine)

    db = _TestSession()
    try:
        db.query(UserPreferenceRecord).filter(UserPreferenceRecord.user_id == 1).delete()
        db.commit()
    finally:
        db.close()

    response = auth_client.get("/api/preferences")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["default_depth"] == "brief"
    assert payload["tone"] == "neutral"
    assert payload["strictness_preference"] == "balanced"
    assert payload["schedule_preference"] == "flexible"

    db = _TestSession()
    try:
        record = db.query(UserPreferenceRecord).filter(UserPreferenceRecord.user_id == 1).first()
        assert record is not None
        assert record.default_depth == "brief"
        assert record.tone == "neutral"
        assert record.strictness_preference == "balanced"
        assert record.schedule_preference == "flexible"
    finally:
        db.close()
    _clear_auth_override()


def test_preferences_retention_policy_purges_stale_record(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("FEATURE_PERSONALIZATION_ENABLED", "true")
    monkeypatch.setenv("PREFERENCES_RETENTION_DAYS", "30")
    Base.metadata.create_all(bind=_test_engine)

    captured_events: list[str] = []

    def _capture_emit(_logger, event, *args, **kwargs):
        captured_events.append(str(event))
        return {"event": event}

    monkeypatch.setattr("docops.api.routes.preferences.emit_event", _capture_emit)

    stale_ts = datetime.now(timezone.utc) - timedelta(days=45)
    db = _TestSession()
    try:
        db.query(UserPreferenceRecord).filter(UserPreferenceRecord.user_id == 1).delete()
        db.add(
            UserPreferenceRecord(
                user_id=1,
                schema_version=1,
                default_depth="deep",
                tone="didactic",
                strictness_preference="strict",
                schedule_preference="intensive",
                created_at=stale_ts,
                updated_at=stale_ts,
            )
        )
        db.commit()
    finally:
        db.close()

    response = auth_client.get("/api/preferences")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_depth"] == "brief"
    assert payload["tone"] == "neutral"
    assert payload["strictness_preference"] == "balanced"
    assert payload["schedule_preference"] == "flexible"
    assert "preferences.retention.purged" in captured_events

    _clear_auth_override()


def test_preferences_update_and_reset_flow(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("FEATURE_PERSONALIZATION_ENABLED", "true")
    Base.metadata.create_all(bind=_test_engine)

    update_response = auth_client.put(
        "/api/preferences",
        json={
            "default_depth": "deep",
            "tone": "didactic",
            "strictness_preference": "strict",
            "schedule_preference": "intensive",
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["default_depth"] == "deep"
    assert update_payload["tone"] == "didactic"
    assert update_payload["strictness_preference"] == "strict"
    assert update_payload["schedule_preference"] == "intensive"

    get_response = auth_client.get("/api/preferences")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["default_depth"] == "deep"
    assert get_payload["tone"] == "didactic"
    assert get_payload["strictness_preference"] == "strict"
    assert get_payload["schedule_preference"] == "intensive"

    reset_response = auth_client.post("/api/preferences/reset")
    assert reset_response.status_code == 200
    reset_payload = reset_response.json()
    assert reset_payload["schema_version"] == 1
    assert reset_payload["default_depth"] == "brief"
    assert reset_payload["tone"] == "neutral"
    assert reset_payload["strictness_preference"] == "balanced"
    assert reset_payload["schedule_preference"] == "flexible"
    _clear_auth_override()


def test_preferences_delete_endpoint_clears_only_current_user(monkeypatch):
    monkeypatch.setenv("FEATURE_PERSONALIZATION_ENABLED", "true")
    Base.metadata.create_all(bind=_test_engine)

    db = _TestSession()
    try:
        db.query(UserPreferenceRecord).filter(UserPreferenceRecord.user_id.in_([101, 202])).delete()
        db.commit()
    finally:
        db.close()

    client_user_101, _ = _make_auth_client_for_user(101)
    response_101 = client_user_101.put(
        "/api/preferences",
        json={
            "default_depth": "deep",
            "tone": "didactic",
            "strictness_preference": "strict",
            "schedule_preference": "intensive",
        },
    )
    assert response_101.status_code == 200
    _clear_auth_override()

    client_user_202, _ = _make_auth_client_for_user(202)
    user_202_get = client_user_202.get("/api/preferences")
    assert user_202_get.status_code == 200
    assert user_202_get.json()["default_depth"] == "brief"

    user_202_delete = client_user_202.delete("/api/preferences")
    assert user_202_delete.status_code == 204
    _clear_auth_override()

    client_user_101_again, _ = _make_auth_client_for_user(101)
    user_101_get = client_user_101_again.get("/api/preferences")
    assert user_101_get.status_code == 200
    assert user_101_get.json()["default_depth"] == "deep"
    assert user_101_get.json()["tone"] == "didactic"
    _clear_auth_override()


def test_preferences_get_migrates_legacy_schema_values(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("FEATURE_PERSONALIZATION_ENABLED", "true")
    Base.metadata.create_all(bind=_test_engine)

    db = _TestSession()
    try:
        db.query(UserPreferenceRecord).filter(UserPreferenceRecord.user_id == 1).delete()
        db.commit()
        db.add(
            UserPreferenceRecord(
                user_id=1,
                schema_version=0,
                default_depth="invalid",
                tone="unknown",
                strictness_preference="x",
                schedule_preference="y",
            )
        )
        db.commit()
    finally:
        db.close()

    response = auth_client.get("/api/preferences")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["default_depth"] == "brief"
    assert payload["tone"] == "neutral"
    assert payload["strictness_preference"] == "balanced"
    assert payload["schedule_preference"] == "flexible"

    db = _TestSession()
    try:
        migrated = db.query(UserPreferenceRecord).filter(UserPreferenceRecord.user_id == 1).first()
        assert migrated is not None
        assert migrated.schema_version == 1
        assert migrated.default_depth == "brief"
        assert migrated.tone == "neutral"
        assert migrated.strictness_preference == "balanced"
        assert migrated.schedule_preference == "flexible"
    finally:
        db.close()
    _clear_auth_override()


def test_chat_stream_disabled_by_feature_flag(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("FEATURE_CHAT_STREAMING_ENABLED", "false")
    resp = auth_client.post("/api/chat/stream", json={"message": "hello"})
    assert resp.status_code == 503
    assert "feature flag" in resp.json()["detail"].lower()
    _clear_auth_override()


def test_chat_returns_only_cited_sources(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Use este trecho [Fonte 2]",
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="chunk um",
                metadata={"file_name": "doc1.pdf", "page": "1", "chunk_id": "c1"},
            ),
            Document(
                page_content="chunk dois",
                metadata={"file_name": "doc2.pdf", "page": "2", "chunk_id": "c2"},
            ),
        ],
    }
    monkeypatch.setattr("docops.api.routes.chat._run_chat", lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state)

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sources"]) == 1
    assert data["sources"][0]["fonte_n"] == 2
    assert data["sources"][0]["file_name"] == "doc2.pdf"
    _clear_auth_override()


def test_chat_quality_signal_low_when_no_retrieval(monkeypatch):
    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Nao encontrei dados suficientes.",
        "intent": "qa",
        "retrieved_chunks": [],
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    signal = resp.json()["quality_signal"]
    assert signal["level"] == "low"
    assert signal["retrieved_count"] == 0
    assert signal["suggested_action"] is not None
    _clear_auth_override()


def test_chat_quality_signal_uses_support_rate_when_available(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Resposta com suporte [Fonte 1]",
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="evidencia forte",
                metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "abc"},
            )
        ],
        "grounding_info": {"support_rate": 0.91, "unsupported_claims": []},
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    signal = resp.json()["quality_signal"]
    assert signal["level"] == "high"
    assert signal["score"] >= 0.8
    assert "support_rate=0.91" in signal["reasons"]
    assert "reason_codes" in signal
    assert "score_components" in signal
    _clear_auth_override()


def test_chat_quality_signal_v2_reason_codes_and_components(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Resposta com suporte [Fonte 1]",
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="evidencia forte",
                metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "abc"},
            )
        ],
        "grounding_info": {"support_rate": 0.91, "unsupported_claims": []},
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    signal = resp.json()["quality_signal"]

    assert set(signal["reason_codes"]) == {
        "support_rate_strong",
        "source_breadth_single",
        "unsupported_claims_none",
        "retrieval_depth_shallow",
    }
    components = signal["score_components"]
    assert set(components.keys()) == {
        "support_rate",
        "source_breadth",
        "unsupported_claims",
        "retrieval_depth",
    }
    assert all(0.0 <= float(value) <= 1.0 for value in components.values())
    assert signal["support_rate"] == 0.91
    assert signal["unsupported_claim_count"] == 0
    _clear_auth_override()


def test_chat_low_confidence_guardrail_applies_constrained_answer(monkeypatch):
    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": (
            "Resposta longa potencialmente especulativa sem evidencias claras. "
            * 30
        ),
        "intent": "qa",
        "retrieved_chunks": [],
        "grounding_info": {"support_rate": 0.21, "unsupported_claims": ["c1", "c2"]},
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    payload = resp.json()
    signal = payload["quality_signal"]

    assert signal["level"] == "low"
    assert "low_confidence_guardrail_applied" in signal["reason_codes"]
    assert "Confiabilidade baixa: resposta em modo conservador." in payload["answer"]
    assert "Proximos passos recomendados:" in payload["answer"]
    assert "Ative o modo strict grounding" in payload["answer"]
    assert len(payload["answer"]) < len(fake_state["answer"])
    assert "Especifique melhor a pergunta" in signal["suggested_action"]
    assert "Adicione ou selecione documentos" in signal["suggested_action"]
    assert "Ative o modo strict grounding" in signal["suggested_action"]
    _clear_auth_override()


def test_chat_low_confidence_guardrail_not_applied_for_high_confidence(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_answer = "Resposta com suporte forte [Fonte 1]"
    fake_state = {
        "answer": fake_answer,
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="evidencia forte",
                metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "abc"},
            )
        ],
        "grounding_info": {"support_rate": 0.91, "unsupported_claims": []},
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    payload = resp.json()
    signal = payload["quality_signal"]
    assert signal["level"] == "high"
    assert payload["answer"] == fake_answer
    assert "low_confidence_guardrail_applied" not in signal["reason_codes"]
    _clear_auth_override()


def test_chat_quality_signal_v2_is_deterministic_for_fixed_input(monkeypatch):
    from langchain_core.documents import Document

    auth_client, _ = _make_auth_client()
    fake_state = {
        "answer": "Resposta deterministica [Fonte 1]",
        "intent": "qa",
        "retrieved_chunks": [
            Document(
                page_content="evidencia deterministica",
                metadata={"file_name": "manual.pdf", "page": "1", "chunk_id": "abc"},
            )
        ],
        "grounding_info": {"support_rate": 0.73, "unsupported_claims": ["claim-1"]},
    }
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: fake_state,
    )

    resp_a = auth_client.post("/api/chat", json={"message": "hello"})
    resp_b = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    signal_a = resp_a.json()["quality_signal"]
    signal_b = resp_b.json()["quality_signal"]
    assert signal_a["score"] == signal_b["score"]
    assert signal_a["level"] == signal_b["level"]
    assert signal_a["reason_codes"] == signal_b["reason_codes"]
    assert signal_a["score_components"] == signal_b["score_components"]
    assert signal_a["suggested_action"] == signal_b["suggested_action"]
    _clear_auth_override()


def test_chat_completed_event_includes_quality_component_metrics(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured_events: list[dict] = []

    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: {
            "answer": "ok",
            "intent": "qa",
            "retrieved_chunks": [],
            "grounding_info": {"support_rate": 0.4, "unsupported_claims": ["c1", "c2"]},
        },
    )

    def _capture_emit_event(_logger, event, level="info", **fields):
        captured_events.append({"event": event, "level": level, **fields})
        return {"event": event, "level": level, **fields}

    monkeypatch.setattr("docops.api.routes.chat.emit_event", _capture_emit_event)

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200

    completed = next(evt for evt in captured_events if evt.get("event") == "chat.request.completed")
    assert "quality_reason_codes" in completed
    assert "quality_component_support_rate" in completed
    assert "quality_component_source_breadth" in completed
    assert "quality_component_unsupported_claims" in completed
    assert "quality_component_retrieval_depth" in completed
    assert "quality_unsupported_claim_count" in completed
    _clear_auth_override()


def test_chat_emits_guardrail_event_when_low_confidence(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured_events: list[dict] = []

    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: {
            "answer": "resposta fraca",
            "intent": "qa",
            "retrieved_chunks": [],
            "grounding_info": {"support_rate": 0.1, "unsupported_claims": ["c1"]},
        },
    )

    def _capture_emit_event(_logger, event, level="info", **fields):
        captured_events.append({"event": event, "level": level, **fields})
        return {"event": event, "level": level, **fields}

    monkeypatch.setattr("docops.api.routes.chat.emit_event", _capture_emit_event)

    resp = auth_client.post("/api/chat", json={"message": "hello", "session_id": "guardrail-s1"})
    assert resp.status_code == 200

    guardrail_event = next(evt for evt in captured_events if evt.get("event") == "chat.low_confidence_guardrail.applied")
    assert guardrail_event["category"] == "chat_quality"
    assert guardrail_event["session_id"] == "guardrail-s1"
    assert guardrail_event["quality_score"] < 0.55
    assert "low_confidence_guardrail_applied" in guardrail_event["quality_reason_codes"]
    _clear_auth_override()


def test_chat_forwards_doc_filters(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}

    def _fake_run(msg, top_k, user_id=0, doc_names=None, strict_grounding=False):
        captured["message"] = msg
        captured["top_k"] = top_k
        captured["user_id"] = user_id
        captured["doc_names"] = doc_names
        return {"answer": "ok", "intent": "qa", "retrieved_chunks": []}

    monkeypatch.setattr("docops.api.routes.chat._run_chat", _fake_run)
    resp = auth_client.post(
        "/api/chat",
        json={"message": "hello", "doc_names": ["a.pdf", "b.pdf"]},
    )
    assert resp.status_code == 200
    assert captured["doc_names"] == ["a.pdf", "b.pdf"]
    _clear_auth_override()


def test_chat_returns_active_context_from_selected_docs(monkeypatch):
    auth_client, _ = _make_auth_client()

    monkeypatch.setattr(
        "docops.db.crud.list_documents_for_user",
        lambda db, user_id: [SimpleNamespace(doc_id="doc-1", file_name="manual.pdf")],
    )
    monkeypatch.setattr(
        "docops.api.routes.chat._run_chat",
        lambda msg, top_k, user_id=0, doc_names=None, strict_grounding=False: {"answer": "ok", "intent": "qa", "retrieved_chunks": []},
    )

    resp = auth_client.post(
        "/api/chat",
        json={"message": "hello", "session_id": "ctx-1", "doc_names": ["doc-1"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["active_context"]["active_doc_ids"] == ["doc-1"]
    assert data["active_context"]["active_doc_names"] == ["manual.pdf"]
    assert data["active_context"]["last_action"] == "rag_answer"
    _clear_auth_override()


def test_artifacts_empty():
    auth_client, _ = _make_auth_client()
    with patch("docops.api.routes.artifact.config") as mock_cfg:
        mock_cfg.artifacts_dir.exists.return_value = False
        resp = auth_client.get("/api/artifacts")
    assert resp.status_code == 200
    assert resp.json() == []
    _clear_auth_override()


def test_artifact_not_found():
    auth_client, _ = _make_auth_client()
    with patch("docops.api.routes.artifact.config") as mock_cfg:
        mock_cfg.artifacts_dir.__truediv__ = lambda self, x: MagicMock(
            exists=lambda: False, is_file=lambda: False
        )
        resp = auth_client.get("/api/artifacts/nonexistent.md")
    assert resp.status_code == 404
    _clear_auth_override()


def test_artifact_template_catalog_returns_expected_blueprints():
    auth_client, _ = _make_auth_client()
    resp = auth_client.get("/api/artifact/templates")
    assert resp.status_code == 200
    data = resp.json()
    template_ids = {item["template_id"] for item in data}
    assert {"brief", "exam_pack", "deep_dossier"}.issubset(template_ids)

    filtered = auth_client.get("/api/artifact/templates", params={"summary_mode": "deep"})
    assert filtered.status_code == 200
    for item in filtered.json():
        assert "deep" in item["summary_modes"]
    _clear_auth_override()


def test_create_artifact_forwards_template_id_and_returns_template_metadata(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}

    def _fake_run(*args, **kwargs):
        if len(args) >= 5:
            captured["template_id"] = args[4]
        else:
            captured["template_id"] = kwargs.get("template_id")
        return {
            "answer": "# Conteudo\n\nChecklist pronto.",
            "filename": "checklist_template.md",
            "path": "artifacts/checklist_template.md",
            "template_id": "exam_pack",
            "template_label": "Exam Prep Pack",
            "template_description": "Pacote para prova",
        }

    monkeypatch.setattr("docops.api.routes.artifact._run_artifact", _fake_run)

    resp = auth_client.post(
        "/api/artifact",
        json={"type": "checklist", "topic": "Revisao final", "template_id": "exam_pack"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_id"] == "exam_pack"
    assert data["template_label"] == "Exam Prep Pack"
    assert captured["template_id"] == "exam_pack"
    _clear_auth_override()


def test_artifact_duplicate_filename_requires_id_for_legacy_routes():
    from docops.db import crud

    # Full-suite CI can mutate app dependency overrides across modules.
    # Pin get_db here so API calls use the same in-memory DB as _TestSession.
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_test_engine)
    auth_client, _ = _make_auth_client()
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / "artifact_a.md"
        path_b = Path(tmpdir) / "artifact_b.md"
        path_a.write_text("conteudo A", encoding="utf-8")
        path_b.write_text("conteudo B", encoding="utf-8")

        db = _TestSession()
        try:
            rec_a = crud.create_artifact_record(
                db,
                user_id=1,
                artifact_type="summary",
                filename="duplicado.md",
                path=str(path_a),
            )
            rec_b = crud.create_artifact_record(
                db,
                user_id=1,
                artifact_type="summary",
                filename="duplicado.md",
                path=str(path_b),
            )
            rec_a_id = rec_a.id
            rec_b_id = rec_b.id
        finally:
            db.close()

        listed = auth_client.get("/api/artifacts")
        assert listed.status_code == 200
        ids = [item["id"] for item in listed.json() if item["filename"] == "duplicado.md"]
        assert rec_a_id in ids and rec_b_id in ids

        legacy = auth_client.get("/api/artifacts/duplicado.md")
        assert legacy.status_code == 409
        detail = legacy.json()["detail"]
        assert detail["error"] == "artifact_filename_ambiguous"
        assert rec_a_id in detail["artifact_ids"]
        assert rec_b_id in detail["artifact_ids"]

        by_id_a = auth_client.get(f"/api/artifacts/id/{rec_a_id}")
        by_id_b = auth_client.get(f"/api/artifacts/id/{rec_b_id}")
        assert by_id_a.status_code == 200
        assert by_id_b.status_code == 200
        assert by_id_a.text == "conteudo A"
        assert by_id_b.text == "conteudo B"

        deleted = auth_client.delete(f"/api/artifacts/id/{rec_a_id}")
        assert deleted.status_code == 204
        assert auth_client.get(f"/api/artifacts/id/{rec_a_id}").status_code == 404
        assert auth_client.get(f"/api/artifacts/id/{rec_b_id}").status_code == 200

    _clear_auth_override()
    app.dependency_overrides[get_db] = _override_get_db


def test_artifacts_list_supports_metadata_filters_and_sort():
    from docops.db import crud

    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_test_engine)
    auth_client, _ = _make_auth_client()

    scope = uuid.uuid4().hex[:10]
    source_doc_a = f"{scope}-doc-a"
    source_doc_b = f"{scope}-doc-b"

    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = Path(tmpdir) / f"{scope}_a.md"
        path_b = Path(tmpdir) / f"{scope}_b.md"
        path_c = Path(tmpdir) / f"{scope}_c.md"
        path_a.write_text("artifact a", encoding="utf-8")
        path_b.write_text("artifact b", encoding="utf-8")
        path_c.write_text("artifact c", encoding="utf-8")

        db = _TestSession()
        try:
            rec_a = crud.create_artifact_record(
                db,
                user_id=1,
                artifact_type="summary",
                title=f"[{scope}] Alpha",
                filename=f"{scope}_alpha.md",
                path=str(path_a),
                template_id="brief",
                generation_profile="summary:brief:brief",
                confidence_level="high",
                confidence_score=0.91,
                source_doc_ids=[source_doc_a],
            )
            rec_b = crud.create_artifact_record(
                db,
                user_id=1,
                artifact_type="checklist",
                title=f"[{scope}] Beta",
                filename=f"{scope}_beta.md",
                path=str(path_b),
                template_id="exam_pack",
                generation_profile="artifact:checklist:exam_pack",
                confidence_level="low",
                confidence_score=0.31,
                source_doc_id=source_doc_b,
                source_doc_ids=[source_doc_b],
            )
            rec_c = crud.create_artifact_record(
                db,
                user_id=1,
                artifact_type="summary",
                title=f"[{scope}] Gamma",
                filename=f"{scope}_gamma.md",
                path=str(path_c),
                template_id="deep_dossier",
                generation_profile="summary:deep:deep_dossier",
                confidence_level="medium",
                confidence_score=0.67,
                source_doc_id=source_doc_a,
                source_doc_ids=[source_doc_a, source_doc_b],
            )
            rec_a_id = rec_a.id
            rec_b_id = rec_b.id
            rec_c_id = rec_c.id
        finally:
            db.close()

        filtered_template = auth_client.get(
            "/api/artifacts",
            params={"template_id": "exam_pack", "search": scope},
        )
        assert filtered_template.status_code == 200
        filtered_template_ids = {item["id"] for item in filtered_template.json()}
        assert rec_b_id in filtered_template_ids
        assert rec_a_id not in filtered_template_ids
        assert rec_c_id not in filtered_template_ids

        filtered_source = auth_client.get(
            "/api/artifacts",
            params={
                "source_doc_id": source_doc_a,
                "sort_by": "confidence_score",
                "sort_order": "desc",
            },
        )
        assert filtered_source.status_code == 200
        filtered_source_ids = [item["id"] for item in filtered_source.json()]
        assert filtered_source_ids[:2] == [rec_a_id, rec_c_id]

        first_item = filtered_source.json()[0]
        assert first_item["generation_profile"] == "summary:brief:brief"
        assert first_item["confidence_level"] == "high"
        assert first_item["confidence_score"] == pytest.approx(0.91, rel=1e-6)
        assert source_doc_a in first_item["source_doc_ids"]
        assert first_item["source_doc_count"] >= 1

        filtered_profile = auth_client.get(
            "/api/artifacts",
            params={"generation_profile": "summary:deep:deep_dossier", "search": scope},
        )
        assert filtered_profile.status_code == 200
        filtered_profile_ids = {item["id"] for item in filtered_profile.json()}
        assert rec_c_id in filtered_profile_ids
        assert rec_a_id not in filtered_profile_ids
        assert rec_b_id not in filtered_profile_ids

    _clear_auth_override()
    app.dependency_overrides[get_db] = _override_get_db


def test_artifact_filter_options_endpoint_returns_metadata_dimensions():
    from docops.db import crud

    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_test_engine)
    auth_client, _ = _make_auth_client()

    scope = uuid.uuid4().hex[:10]
    source_doc_a = f"{scope}-opt-a"
    source_doc_b = f"{scope}-opt-b"
    profile = f"summary:deep:{scope}"

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / f"{scope}_options.md"
        file_path.write_text("artifact options", encoding="utf-8")

        db = _TestSession()
        try:
            crud.create_artifact_record(
                db,
                user_id=1,
                artifact_type=f"summary_{scope}",
                title=f"[{scope}] Filter Options",
                filename=f"{scope}_options.md",
                path=str(file_path),
                template_id=f"template_{scope}",
                generation_profile=profile,
                confidence_level="high",
                confidence_score=0.88,
                source_doc_id=source_doc_a,
                source_doc_ids=[source_doc_a, source_doc_b],
            )
        finally:
            db.close()

        response = auth_client.get("/api/artifacts/filters")
        assert response.status_code == 200
        payload = response.json()
        assert f"summary_{scope}" in payload["artifact_types"]
        assert f"template_{scope}" in payload["template_ids"]
        assert profile in payload["generation_profiles"]
        assert source_doc_a in payload["source_doc_ids"]
        assert source_doc_b in payload["source_doc_ids"]
        assert "high" in payload["confidence_levels"]

    _clear_auth_override()
    app.dependency_overrides[get_db] = _override_get_db


def test_chat_to_artifact_endpoint_requires_feature_flag(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.delenv("FEATURE_PREMIUM_CHAT_TO_ARTIFACT_ENABLED", raising=False)

    resp = auth_client.post(
        "/api/artifact/from-chat",
        json={"answer": "Resumo de teste", "session_id": "session-flag-off", "turn_ref": "turn-1"},
    )
    assert resp.status_code == 503
    assert "disabled" in str(resp.json().get("detail", "")).lower()
    _clear_auth_override()


def test_chat_to_artifact_one_click_creates_linked_artifact(monkeypatch):
    from docops.db import crud

    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_test_engine)
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("FEATURE_PREMIUM_CHAT_TO_ARTIFACT_ENABLED", "true")

    scope = uuid.uuid4().hex[:10]
    session_ref = f"session-{scope}"
    turn_ref = f"{session_ref}:7"
    doc_id = f"{scope}-doc-id"
    doc_name = f"{scope}-manual.md"

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)

        def _fake_writer(filename: str, content: str, user_id: int) -> Path:
            out = base_dir / filename
            out.write_text(content, encoding="utf-8")
            return out

        monkeypatch.setattr("docops.tools.doc_tools.tool_write_artifact", _fake_writer)

        db = _TestSession()
        try:
            crud.create_document_record(
                db,
                user_id=1,
                doc_id=doc_id,
                file_name=doc_name,
                source_path=str(base_dir / "source.txt"),
                storage_path=str(base_dir / "stored.txt"),
                file_type="md",
                chunk_count=10,
            )
        finally:
            db.close()

        response = auth_client.post(
            "/api/artifact/from-chat",
            json={
                "answer": "## Resumo Aprofundado\n\nConteudo detalhado do chat.",
                "title": f"{scope} resumo aprofundado",
                "user_prompt": "faca um resumo aprofundado deste documento",
                "session_id": session_ref,
                "turn_ref": turn_ref,
                "doc_ids": [doc_id],
                "doc_names": [doc_name],
                "confidence_level": "high",
                "confidence_score": 0.93,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["artifact_id"] is not None
        assert payload["filename"].endswith(".md")
        assert payload["conversation_session_id"] == session_ref
        assert payload["conversation_turn_ref"] == turn_ref

        listed = auth_client.get(
            "/api/artifacts",
            params={"conversation_session_id": session_ref},
        )
        assert listed.status_code == 200
        items = listed.json()
        assert any(item["id"] == payload["artifact_id"] for item in items)

        created = next(item for item in items if item["id"] == payload["artifact_id"])
        assert created["conversation_session_id"] == session_ref
        assert created["conversation_turn_ref"] == turn_ref
        assert doc_id in created["source_doc_ids"]

    _clear_auth_override()
    app.dependency_overrides[get_db] = _override_get_db


def test_alembic_upgrade_creates_supported_schema(tmp_path):
    from docops.db.database import run_db_migrations

    db_file = tmp_path / "migr_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    assert run_db_migrations(db_url) is True

    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert "alembic_version" in table_names
        assert "users" in table_names
        assert "documents" in table_names
        assert "artifacts" in table_names
    finally:
        engine.dispose()


def test_summarize_debug_true_includes_diagnostics(monkeypatch):
    auth_client, _ = _make_auth_client()

    fake_doc = MagicMock(file_name="manual.pdf", doc_id="doc-uuid-1")
    monkeypatch.setattr("docops.api.routes.summarize.require_user_document", lambda *_a, **_k: fake_doc)

    def _fake_run(*_args, **_kwargs):
        return {
            "answer": "Resumo profundo.",
            "artifact_path": None,
            "artifact_filename": None,
            "diagnostics": {"coverage": {"overall_coverage_score": 0.92}},
        }

    monkeypatch.setattr("docops.api.routes.summarize._run_summarize", _fake_run)

    resp = auth_client.post(
        "/api/summarize",
        json={"doc": "manual.pdf", "summary_mode": "deep", "debug_summary": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Resumo profundo."
    assert data["summary_diagnostics"] is not None
    assert data["summary_diagnostics"]["coverage"]["overall_coverage_score"] == 0.92
    _clear_auth_override()


def test_summarize_forwards_template_id_and_returns_template_metadata(monkeypatch):
    auth_client, _ = _make_auth_client()
    fake_doc = MagicMock(file_name="manual.pdf", doc_id="doc-uuid-1")
    monkeypatch.setattr("docops.api.routes.summarize.require_user_document", lambda *_a, **_k: fake_doc)
    captured: dict = {}

    def _fake_run(*args, **kwargs):
        if len(args) >= 6:
            captured["template_id"] = args[5]
        else:
            captured["template_id"] = kwargs.get("template_id")
        return {
            "answer": "Resumo com template.",
            "artifact_path": None,
            "artifact_filename": None,
            "template_id": "deep_dossier",
            "template_label": "Dossie Analitico",
            "template_description": "Analise profunda",
            "diagnostics": None,
        }

    monkeypatch.setattr("docops.api.routes.summarize._run_summarize", _fake_run)

    resp = auth_client.post(
        "/api/summarize",
        json={
            "doc": "manual.pdf",
            "summary_mode": "deep",
            "template_id": "deep_dossier",
            "debug_summary": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert captured["template_id"] == "deep_dossier"
    assert data["template_id"] == "deep_dossier"
    assert data["template_label"] == "Dossie Analitico"
    _clear_auth_override()


def test_summarize_debug_false_hides_diagnostics(monkeypatch):
    auth_client, _ = _make_auth_client()

    fake_doc = MagicMock(file_name="manual.pdf", doc_id="doc-uuid-1")
    monkeypatch.setattr("docops.api.routes.summarize.require_user_document", lambda *_a, **_k: fake_doc)

    def _fake_run(*_args, **_kwargs):
        return {
            "answer": "Resumo profundo.",
            "artifact_path": None,
            "artifact_filename": None,
            "diagnostics": {"coverage": {"overall_coverage_score": 0.92}},
        }

    monkeypatch.setattr("docops.api.routes.summarize._run_summarize", _fake_run)

    resp = auth_client.post(
        "/api/summarize",
        json={"doc": "manual.pdf", "summary_mode": "deep", "debug_summary": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Resumo profundo."
    assert data["summary_diagnostics"] is None
    _clear_auth_override()


def test_summarize_strict_gate_returns_422_when_fail_closed_enabled(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("SUMMARY_FAIL_CLOSED_STRICT", "true")

    fake_doc = MagicMock(file_name="manual.pdf", doc_id="doc-uuid-1")
    monkeypatch.setattr("docops.api.routes.summarize.require_user_document", lambda *_a, **_k: fake_doc)

    monkeypatch.setattr(
        "docops.api.routes.summarize._run_summarize",
        lambda *_a, **_k: {
            "answer": "Resumo bloqueado.",
            "artifact_path": None,
            "artifact_filename": None,
            "diagnostics": {
                "profile_used": "strict",
                "final": {
                    "accepted": False,
                    "blocking_reasons": ["missing_must_cover_topics"],
                },
            },
        },
    )

    resp = auth_client.post(
        "/api/summarize",
        json={"doc": "manual.pdf", "summary_mode": "deep", "debug_summary": True},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "deep_summary_quality_gate_failed"
    assert "missing_must_cover_topics" in detail["blocking_reasons"]
    _clear_auth_override()


def test_summarize_strict_gate_returns_200_when_fail_closed_disabled(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("SUMMARY_FAIL_CLOSED_STRICT", "false")

    fake_doc = MagicMock(file_name="manual.pdf", doc_id="doc-uuid-1")
    monkeypatch.setattr("docops.api.routes.summarize.require_user_document", lambda *_a, **_k: fake_doc)

    monkeypatch.setattr(
        "docops.api.routes.summarize._run_summarize",
        lambda *_a, **_k: {
            "answer": "Resumo liberado.",
            "artifact_path": None,
            "artifact_filename": None,
            "diagnostics": {
                "profile_used": "strict",
                "final": {
                    "accepted": False,
                    "blocking_reasons": ["missing_must_cover_topics"],
                },
            },
        },
    )

    resp = auth_client.post(
        "/api/summarize",
        json={"doc": "manual.pdf", "summary_mode": "deep", "debug_summary": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Resumo liberado."
    assert data["summary_diagnostics"]["profile_used"] == "strict"
    _clear_auth_override()


def test_summarize_strict_gate_returns_200_with_jsonable_diagnostics(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("SUMMARY_FAIL_CLOSED_STRICT", "false")

    fake_doc = MagicMock(file_name="manual.pdf", doc_id="doc-uuid-1")
    monkeypatch.setattr("docops.api.routes.summarize.require_user_document", lambda *_a, **_k: fake_doc)

    # Diagnostics may include non-JSON-native containers from runtime pipeline.
    # Route must sanitize before returning to avoid 500 in strict-off mode.
    monkeypatch.setattr(
        "docops.api.routes.summarize._run_summarize",
        lambda *_a, **_k: {
            "answer": "Resumo liberado.",
            "artifact_path": None,
            "artifact_filename": None,
            "diagnostics": {
                "profile_used": "strict",
                "final": {
                    "accepted": False,
                    "blocking_reasons": {"missing_must_cover_topics"},
                },
            },
        },
    )

    resp = auth_client.post(
        "/api/summarize",
        json={"doc": "manual.pdf", "summary_mode": "deep", "debug_summary": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Resumo liberado."
    assert data["summary_diagnostics"]["profile_used"] == "strict"
    assert data["summary_diagnostics"]["final"]["blocking_reasons"] == ["missing_must_cover_topics"]
    _clear_auth_override()


def test_studyplan_500_payload_is_sanitized(monkeypatch):
    auth_client, _ = _make_auth_client()

    def _boom(*_a, **_k):
        raise RuntimeError("segredo_interno_nao_deve_vazar")

    monkeypatch.setattr("docops.api.routes.studyplan._generate_plan", _boom)

    resp = auth_client.post(
        "/api/studyplan",
        json={"topic": "Algebra Linear", "days": 7, "doc_names": []},
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Erro interno ao gerar plano de estudos."
    _clear_auth_override()


def test_pipeline_evaluate_answer_500_payload_is_sanitized(monkeypatch):
    auth_client, _ = _make_auth_client()

    def _boom(*_a, **_k):
        raise RuntimeError("token_interno")

    monkeypatch.setattr("docops.api.routes.pipeline._run_evaluate_answer", _boom)

    resp = auth_client.post(
        "/api/pipeline/evaluate-answer",
        json={
            "question": "Qual e a capital da Franca?",
            "user_answer": "Paris",
            "answer_hint": "Capital francesa",
        },
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Erro interno ao avaliar resposta."
    _clear_auth_override()


def test_pipeline_gap_analysis_500_payload_is_sanitized(monkeypatch):
    auth_client, _ = _make_auth_client()

    monkeypatch.setattr(
        "docops.api.routes.pipeline.crud.list_documents_for_user",
        lambda *_args, **_kwargs: [SimpleNamespace(file_name="manual.pdf", doc_id="doc-1", chunk_count=1)],
    )

    def _boom(*_a, **_k):
        raise RuntimeError("detalhe_interno_nao_deve_vazar")

    monkeypatch.setattr("docops.api.routes.pipeline._run_gap_analysis_with_thread_session", _boom)

    resp = auth_client.post("/api/pipeline/gap-analysis", json={"doc_names": []})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Erro interno ao executar análise de lacunas."
    _clear_auth_override()


def test_calendar_reminder_crud():
    auth_client, _ = _make_auth_client()
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    end = start + timedelta(hours=1)

    created = auth_client.post(
        "/api/calendar/reminders",
        json={
            "title": "Revisar capitulo",
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "note": "Arvores de decisao",
            "all_day": False,
        },
    )
    assert created.status_code == 200
    reminder_id = created.json()["id"]

    listed = auth_client.get("/api/calendar/reminders")
    assert listed.status_code == 200
    assert any(item["id"] == reminder_id for item in listed.json())

    updated = auth_client.put(
        f"/api/calendar/reminders/{reminder_id}",
        json={
            "title": "Revisar capitulo 7",
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "note": "Checklist final",
            "all_day": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Revisar capitulo 7"

    deleted = auth_client.delete(f"/api/calendar/reminders/{reminder_id}")
    assert deleted.status_code == 200
    _clear_auth_override()


def test_calendar_schedule_overview():
    auth_client, _ = _make_auth_client()
    today_weekday = datetime.now(timezone.utc).weekday()

    created = auth_client.post(
        "/api/calendar/schedules",
        json={
            "title": "Estudo de ML",
            "day_of_week": today_weekday,
            "start_time": "14:00",
            "end_time": "16:00",
            "note": "Aula pratica",
            "active": True,
        },
    )
    assert created.status_code == 200
    assert created.json()["day_of_week"] == today_weekday

    overview = auth_client.get("/api/calendar/overview")
    assert overview.status_code == 200
    data = overview.json()
    assert "today_schedule" in data
    assert any(item["title"] == "Estudo de ML" for item in data["today_schedule"])
    _clear_auth_override()


def test_chat_calendar_query_bypasses_llm(monkeypatch):
    auth_client, _ = _make_auth_client()

    def _fail_llm(*_args, **_kwargs):
        raise AssertionError("_run_chat should not be called for calendar query")

    monkeypatch.setattr("docops.api.routes.chat._run_chat", _fail_llm)
    # Mock orchestrator (pass-through) e calendar assistant (resposta sem chamar Gemini)
    monkeypatch.setattr(
        "docops.services.orchestrator.maybe_orchestrate",
        lambda msg, uid, db, history=None, session_id=None, active_context=None: None,
    )
    monkeypatch.setattr(
        "docops.api.routes.chat.maybe_answer_calendar_query",
        lambda msg, uid, db, history=None: {
            "answer": "Para hoje, não encontrei compromissos no seu calendário.",
            "intent": "calendar",
            "sources": [],
            "calendar_action": None,
        },
    )
    resp = auth_client.post("/api/chat", json={"message": "Tenho compromisso hoje na agenda?"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["intent"] == "calendar"
    assert "hoje" in payload["answer"].lower() or "calendario" in payload["answer"].lower()
    _clear_auth_override()


def test_chat_forwards_strict_grounding(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}

    def _fake_run(msg, top_k, user_id=0, doc_names=None, strict_grounding=False):
        captured["strict_grounding"] = strict_grounding
        return {"answer": "ok", "intent": "qa", "retrieved_chunks": []}

    monkeypatch.setattr("docops.api.routes.chat._run_chat", _fake_run)
    resp = auth_client.post(
        "/api/chat",
        json={"message": "explique", "strict_grounding": True},
    )
    assert resp.status_code == 200
    assert captured["strict_grounding"] is True
    _clear_auth_override()


def test_ingest_path_rejects_prefix_bypass(monkeypatch):
    auth_client, _ = _make_auth_client()

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        allowed_dir = root / "allowed"
        bypass_dir = root / "allowed_evil"
        allowed_dir.mkdir(parents=True, exist_ok=True)
        bypass_dir.mkdir(parents=True, exist_ok=True)

        bypass_file = bypass_dir / "outside.txt"
        bypass_file.write_text("outside", encoding="utf-8")

        monkeypatch.setenv("INGEST_ALLOWED_DIRS", str(allowed_dir))

        def _fail_ingest(*_args, **_kwargs):
            raise AssertionError("_run_ingest should not be called for disallowed paths")

        monkeypatch.setattr("docops.api.routes.ingest._run_ingest", _fail_ingest)

        resp = auth_client.post("/api/ingest", json={"path": str(bypass_file)})
        assert resp.status_code == 403

    _clear_auth_override()


def test_ingest_upload_rejects_oversized_file(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("INGEST_UPLOAD_MAX_BYTES", "8")

    def _fail_ingest(*_args, **_kwargs):
        raise AssertionError("_run_ingest should not run when upload exceeds limit")

    monkeypatch.setattr("docops.api.routes.ingest._run_ingest", _fail_ingest)

    resp = auth_client.post(
        "/api/ingest/upload",
        data={"chunk_size": "0", "chunk_overlap": "0"},
        files=[("files", ("big.txt", b"123456789", "text/plain"))],
    )

    assert resp.status_code == 413
    assert "maximum size" in resp.json()["detail"]
    _clear_auth_override()


def test_ingest_photo_rejects_oversized_file(monkeypatch):
    auth_client, _ = _make_auth_client()
    monkeypatch.setenv("INGEST_PHOTO_MAX_BYTES", "8")

    def _fail_ocr(*_args, **_kwargs):
        raise AssertionError("OCR should not run when image exceeds upload limit")

    monkeypatch.setattr("docops.api.routes.ingest._ocr_with_gemini", _fail_ocr)

    resp = auth_client.post(
        "/api/ingest/photo",
        data={"title": "foto"},
        files={"file": ("imagem.png", b"123456789", "image/png")},
    )

    assert resp.status_code == 413
    assert "maximum size" in resp.json()["detail"]
    _clear_auth_override()


def test_delete_doc_does_not_unlink_external_source(monkeypatch):
    auth_client, fake_user = _make_auth_client()
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_test_engine)
    monkeypatch.setattr("docops.ingestion.indexer.delete_doc_from_index", lambda **_kwargs: None, raising=False)

    from docops.db.crud import create_document_record, get_document_by_user_and_doc_id

    with tempfile.TemporaryDirectory() as tmpdir:
        external_file = Path(tmpdir) / "external_source.txt"
        external_file.write_text("conteudo externo", encoding="utf-8")
        doc_id = f"doc-external-{uuid.uuid4().hex}"

        with _TestSession() as db:
            create_document_record(
                db,
                user_id=fake_user.id,
                doc_id=doc_id,
                file_name=external_file.name,
                source_path=str(external_file),
                storage_path=str(external_file),
                file_type="txt",
                chunk_count=1,
            )

        resp = auth_client.delete(f"/api/docs/{doc_id}")
        assert resp.status_code == 204
        assert external_file.exists()

        with _TestSession() as db:
            assert get_document_by_user_and_doc_id(db, fake_user.id, doc_id) is None

    _clear_auth_override()


def test_artifact_pdf_temp_file_is_cleaned_up(monkeypatch):
    auth_client, fake_user = _make_auth_client()
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_test_engine)

    from docops.db.crud import create_artifact_record
    from docops.storage.paths import get_user_artifacts_dir

    artifacts_dir = get_user_artifacts_dir(fake_user.id)
    artifact_name = f"artifact_{uuid.uuid4().hex}.md"
    artifact_path = artifacts_dir / artifact_name
    artifact_path.write_text("# Titulo\n\nConteudo", encoding="utf-8")

    with _TestSession() as db:
        create_artifact_record(
            db,
            user_id=fake_user.id,
            artifact_type="summary",
            filename=artifact_name,
            path=str(artifact_path),
            title="Resumo",
        )

    temp_pdf_path = artifacts_dir / f"tmp_pdf_{uuid.uuid4().hex}.pdf"

    class _FakeNamedTempFile:
        def __init__(self, name: Path):
            self.name = str(name)

        def close(self) -> None:
            pass

    def _fake_named_tempfile(*_args, **_kwargs):
        temp_pdf_path.write_bytes(b"")
        return _FakeNamedTempFile(temp_pdf_path)

    def _fake_markdown_to_pdf(_content: str, output_path: Path) -> None:
        Path(output_path).write_bytes(b"%PDF-1.4\n%%EOF")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", _fake_named_tempfile)
    monkeypatch.setattr("docops.tools.doc_tools._markdown_to_pdf", _fake_markdown_to_pdf)

    resp = auth_client.get(f"/api/artifacts/{artifact_name}/pdf")
    assert resp.status_code == 200
    _ = resp.content
    assert not temp_pdf_path.exists()

    artifact_path.unlink(missing_ok=True)

def test_chat_to_thread_uses_local_session(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}
    request_db_ref: dict = {}

    def _tracking_get_db():
        Base.metadata.create_all(bind=_test_engine)
        db = _TestSession()
        request_db_ref["db"] = db
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _tracking_get_db

    monkeypatch.setattr(
        "docops.api.routes.chat._resolve_doc_context",
        lambda *_args, **_kwargs: {"active_doc_ids": [], "active_doc_names": []},
    )

    def _fake_orchestrate(message, user_id, db, history=None, session_id=None, active_context=None):
        captured["thread_db"] = db
        return {"answer": "ok", "intent": "action"}

    monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", _fake_orchestrate)

    resp = auth_client.post("/api/chat", json={"message": "crie uma tarefa"})
    assert resp.status_code == 200
    assert captured["thread_db"] is not request_db_ref["db"]
    assert hasattr(captured["thread_db"], "close")

    app.dependency_overrides[get_db] = _override_get_db
    _clear_auth_override()


def test_pipeline_digest_to_thread_uses_local_session(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}
    request_db_ref: dict = {}

    def _tracking_get_db():
        Base.metadata.create_all(bind=_test_engine)
        db = _TestSession()
        request_db_ref["db"] = db
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _tracking_get_db

    monkeypatch.setattr(
        "docops.api.routes.pipeline.require_user_document",
        lambda *_args, **_kwargs: SimpleNamespace(file_name="manual.pdf", doc_id="doc-1"),
    )

    def _fake_run_digest(
        doc_name,
        doc_id,
        user_id,
        generate_flashcards,
        extract_tasks,
        num_cards,
        max_tasks,
        db,
        schedule_reviews=False,
    ):
        captured["thread_db"] = db
        return {
            "summary": "Resumo",
            "deck_id": None,
            "tasks_created": 0,
            "task_titles": [],
            "reviews_scheduled": 0,
        }

    monkeypatch.setattr("docops.api.routes.pipeline._run_digest", _fake_run_digest)

    resp = auth_client.post("/api/pipeline/digest", json={"doc_name": "manual.pdf"})
    assert resp.status_code == 200
    assert captured["thread_db"] is not request_db_ref["db"]

    app.dependency_overrides[get_db] = _override_get_db
    _clear_auth_override()


def test_pipeline_gap_analysis_to_thread_uses_local_session(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}
    request_db_ref: dict = {}

    def _tracking_get_db():
        Base.metadata.create_all(bind=_test_engine)
        db = _TestSession()
        request_db_ref["db"] = db
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _tracking_get_db

    monkeypatch.setattr(
        "docops.api.routes.pipeline.crud.list_documents_for_user",
        lambda *_args, **_kwargs: [SimpleNamespace(file_name="manual.pdf", doc_id="doc-1", chunk_count=1)],
    )

    def _fake_run_gap_analysis(user_id, doc_names, db):
        captured["thread_db"] = db
        return [
            {
                "topico": "Topico",
                "descricao": "Descricao",
                "prioridade": "normal",
                "sugestao": "Sugestao",
            }
        ]

    monkeypatch.setattr("docops.api.routes.pipeline._run_gap_analysis", _fake_run_gap_analysis)

    resp = auth_client.post("/api/pipeline/gap-analysis", json={"doc_names": []})
    assert resp.status_code == 200
    assert captured["thread_db"] is not request_db_ref["db"]

    app.dependency_overrides[get_db] = _override_get_db
    _clear_auth_override()


def test_pipeline_study_plan_to_thread_uses_local_session(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}
    request_db_ref: dict = {}

    def _tracking_get_db():
        Base.metadata.create_all(bind=_test_engine)
        db = _TestSession()
        request_db_ref["db"] = db
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _tracking_get_db

    monkeypatch.setattr(
        "docops.api.routes.pipeline.require_user_document",
        lambda *_args, **_kwargs: SimpleNamespace(file_name="manual.pdf", doc_id="doc-1"),
    )

    def _fake_generate_study_plan(
        doc_name,
        doc_id,
        user_id,
        hours_per_day,
        deadline,
        db,
        generate_flashcards=True,
        num_cards=15,
        preferred_start_time="20:00",
    ):
        captured["thread_db"] = db
        return {
            "plan_text": "Plano",
            "tasks_created": 1,
            "reminders_created": 1,
            "sessions_count": 1,
            "deck_id": None,
            "titulo": "Plano",
            "conflicts": [],
        }

    monkeypatch.setattr(
        "docops.services.study_plan_generator.generate_study_plan",
        _fake_generate_study_plan,
    )
    monkeypatch.setattr(
        "docops.api.routes.pipeline.crud.create_study_plan_record",
        lambda *_args, **_kwargs: SimpleNamespace(id=123),
    )

    future_date = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    resp = auth_client.post(
        "/api/pipeline/study-plan",
        json={
            "doc_name": "manual.pdf",
            "hours_per_day": 2,
            "deadline_date": future_date,
            "generate_flashcards": False,
            "num_cards": 10,
            "preferred_start_time": "20:00",
        },
    )
    assert resp.status_code == 200
    assert captured["thread_db"] is not request_db_ref["db"]

    app.dependency_overrides[get_db] = _override_get_db
    _clear_auth_override()


def test_concurrent_chat_and_pipeline_thread_sessions(monkeypatch):
    auth_client, _ = _make_auth_client()
    chat_db_ids: list[int] = []
    digest_db_ids: list[int] = []
    lock = Lock()
    Base.metadata.create_all(bind=_test_engine)

    def _thread_safe_get_db():
        db = _TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _thread_safe_get_db

    monkeypatch.setattr(
        "docops.api.routes.chat._resolve_doc_context",
        lambda *_args, **_kwargs: {"active_doc_ids": [], "active_doc_names": []},
    )

    def _fake_orchestrate(message, user_id, db, history=None, session_id=None, active_context=None):
        with lock:
            chat_db_ids.append(id(db))
        return {"answer": "ok", "intent": "action"}

    monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", _fake_orchestrate)
    monkeypatch.setattr(
        "docops.api.routes.pipeline.require_user_document",
        lambda *_args, **_kwargs: SimpleNamespace(file_name="manual.pdf", doc_id="doc-1"),
    )

    def _fake_run_digest(
        doc_name,
        doc_id,
        user_id,
        generate_flashcards,
        extract_tasks,
        num_cards,
        max_tasks,
        db,
        schedule_reviews=False,
    ):
        with lock:
            digest_db_ids.append(id(db))
        return {
            "summary": "Resumo",
            "deck_id": None,
            "tasks_created": 0,
            "task_titles": [],
            "reviews_scheduled": 0,
        }

    monkeypatch.setattr("docops.api.routes.pipeline._run_digest", _fake_run_digest)

    def _hit_chat(i: int) -> int:
        return auth_client.post("/api/chat", json={"message": f"msg {i}"}).status_code

    def _hit_digest(i: int) -> int:
        return auth_client.post("/api/pipeline/digest", json={"doc_name": "manual.pdf"}).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        chat_status = list(pool.map(_hit_chat, range(3)))
        digest_status = list(pool.map(_hit_digest, range(3)))

    assert all(code == 200 for code in chat_status + digest_status)
    assert len(chat_db_ids) == 3
    assert len(digest_db_ids) == 3
    assert len(set(chat_db_ids)) >= 2
    assert len(set(digest_db_ids)) >= 2

    app.dependency_overrides[get_db] = _override_get_db
    _clear_auth_override()

