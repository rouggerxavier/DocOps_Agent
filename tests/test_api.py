"""Smoke tests da API — com suporte a auth."""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch

# Setar vars antes de qualquer import da app
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from docops.api.app import app
from docops.auth.dependencies import get_current_user
from docops.db.database import Base, get_db
from docops.db.models import User


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


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)


# ── Health (público) ──────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


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
    monkeypatch.setattr("docops.api.routes.chat._run_chat", lambda msg, top_k: fake_state)
    resp = auth_client.post("/api/chat", json={"message": "hello", "session_id": "s1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Test answer [Fonte 1]"
    assert data["intent"] == "qa"
    assert len(data["sources"]) == 1
    assert data["sources"][0]["file_name"] == "manual.pdf"
    assert data["session_id"] == "s1"
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
