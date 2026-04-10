"""Smoke tests da API — com suporte a auth."""

from __future__ import annotations

import os
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
    monkeypatch.setattr("docops.api.routes.chat._run_chat", lambda msg, top_k: fake_state)

    resp = auth_client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sources"]) == 1
    assert data["sources"][0]["fonte_n"] == 2
    assert data["sources"][0]["file_name"] == "doc2.pdf"
    _clear_auth_override()


def test_chat_forwards_doc_filters(monkeypatch):
    auth_client, _ = _make_auth_client()
    captured: dict = {}

    def _fake_run(msg, top_k, user_id=0, doc_names=None):
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
        lambda msg, top_k, user_id=0, doc_names=None: {"answer": "ok", "intent": "qa", "retrieved_chunks": []},
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
        lambda msg, uid, db: None,
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
