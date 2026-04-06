"""Testes de roteamento de intenções para calendário.

Garante que pedidos de calendário, lembrete e rotina nunca caiam
em notas ou tarefas por engano, e que comportamentos existentes
(plano de estudos, flashcards, RAG) continuem funcionando.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

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

# ── DB em memória ──────────────────────────────────────────────────────────────

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

_fake_user = User(
    id=99, name="Tester", email="tester_cal@example.com",
    password_hash="x", is_active=True,
)


def _make_auth_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _fake_user
    return TestClient(app)


def _clear_auth():
    app.dependency_overrides.pop(get_current_user, None)


# Respostas padrão de mock
_REMINDER_RESPONSE = {
    "answer": "✅ Lembrete criado com sucesso!\n\n**Hoje é feriado**\n📅 03/04/2026 às 14:00",
    "intent": "calendar_create_reminder",
    "sources": [],
    "calendar_action": {
        "type": "reminder_created",
        "id": 1,
        "title": "Hoje é feriado",
        "date": "03/04/2026",
        "time": "14:00",
    },
}

_SCHEDULE_RESPONSE = {
    "answer": "✅ Cronograma semanal criado!\n- **Estágio** — Segunda-feira, 08:00 às 12:00",
    "intent": "calendar_create_schedule",
    "sources": [],
    "calendar_action": {"type": "schedule_created", "blocks": []},
}

_CLARIFICATION_RESPONSE = {
    "answer": "Quais são os horários da sua rotina?",
    "intent": "calendar_clarification",
    "sources": [],
    "calendar_action": None,
}


# ── Testes de roteamento via HTTP ──────────────────────────────────────────────


class TestCalendarRouting:
    """Cenários onde o chat deve criar eventos no calendário, nunca em notas/tarefas."""

    def test_lembrete_explicito_no_calendario(self, monkeypatch):
        """'lembrete no calendário para as 14h dizendo que hoje é feriado' → calendário."""
        # Orchestrator retorna None (pass-through)
        monkeypatch.setattr(
            "docops.services.orchestrator.maybe_orchestrate",
            lambda msg, uid, db: None,
        )
        # Calendar assistant cria o lembrete
        monkeypatch.setattr(
            "docops.api.routes.chat.maybe_answer_calendar_query",
            lambda msg, uid, db, history=None: _REMINDER_RESPONSE,
        )

        client = _make_auth_client()
        resp = client.post("/api/chat", json={
            "message": "quero criar um lembrete no calendário para as 14 horas dizendo que hoje é feriado"
        })
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        intent = payload.get("intent", "")
        assert "calendar" in intent, f"Esperava intent de calendário, recebi: {intent}"
        assert "nota" not in intent
        assert "tarefa" not in intent
        cal_action = payload.get("calendar_action")
        assert cal_action is not None, "calendar_action deve estar presente"
        assert cal_action.get("type") == "reminder_created"

    def test_criar_rotina_sem_detalhes_pede_clarificacao(self, monkeypatch):
        """'quero criar minha rotina' sem horários → clarificação de calendário, não nota/tarefa."""
        monkeypatch.setattr(
            "docops.services.orchestrator.maybe_orchestrate",
            lambda msg, uid, db: None,
        )
        monkeypatch.setattr(
            "docops.api.routes.chat.maybe_answer_calendar_query",
            lambda msg, uid, db, history=None: _CLARIFICATION_RESPONSE,
        )

        client = _make_auth_client()
        resp = client.post("/api/chat", json={"message": "quero criar minha rotina"})
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        intent = payload.get("intent", "")
        assert intent in ("calendar_clarification", "calendar_create_schedule", "calendar"), \
            f"Esperava intent de calendário/clarificação, recebi: {intent}"
        assert "nota" not in intent
        assert "tarefa" not in intent

    def test_blocos_recorrentes_viram_schedule(self, monkeypatch):
        """'segunda a sexta 08:00-12:00 estágio; ...' → create_schedule no calendário."""
        monkeypatch.setattr(
            "docops.services.orchestrator.maybe_orchestrate",
            lambda msg, uid, db: None,
        )
        monkeypatch.setattr(
            "docops.api.routes.chat.maybe_answer_calendar_query",
            lambda msg, uid, db, history=None: _SCHEDULE_RESPONSE,
        )

        client = _make_auth_client()
        resp = client.post("/api/chat", json={
            "message": (
                "segunda a sexta 08:00-12:00 estágio; "
                "12:00-14:00 almoço; 14:00-18:00 faculdade; "
                "faculdade só segunda a quinta"
            )
        })
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        intent = payload.get("intent", "")
        assert "calendar" in intent, f"Esperava intent de calendário, recebi: {intent}"
        cal_action = payload.get("calendar_action")
        assert cal_action is not None
        assert cal_action.get("type") == "schedule_created"

    def test_correcao_explicita_vai_para_calendario(self, monkeypatch):
        """'não é nas notas, é no calendário' → orchestrator passa para calendar_assistant."""
        orchestrator_calls = []

        def _spy_orchestrate(msg, uid, db):
            orchestrator_calls.append(msg)
            return None  # pass-through esperado

        monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", _spy_orchestrate)
        monkeypatch.setattr(
            "docops.api.routes.chat.maybe_answer_calendar_query",
            lambda msg, uid, db, history=None: _CLARIFICATION_RESPONSE,
        )

        client = _make_auth_client()
        resp = client.post("/api/chat", json={"message": "não é nas notas, é no calendário"})
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        intent = payload.get("intent", "")
        assert "calendar" in intent, f"Esperava intent de calendário, recebi: {intent}"
        assert len(orchestrator_calls) == 1  # orchestrator foi chamado mas fez pass-through

    def test_nota_explicita_vai_para_nota(self, monkeypatch):
        """'anota isso nas notas: revisar capítulo 3' → nota (não calendário)."""

        def _fake_orchestrate(msg, uid, db):
            return {
                "answer": "📝 Nota criada: **Nota: revisar capítulo 3**\n[Ver Notas →](/notes)",
                "intent": "cascade_create_note",
            }

        monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", _fake_orchestrate)

        client = _make_auth_client()
        resp = client.post("/api/chat", json={
            "message": "anota isso nas notas: revisar capítulo 3"
        })
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        intent = payload.get("intent", "")
        assert "note" in intent or "nota" in intent or "cascade_create_note" in intent, \
            f"Esperava intent de nota, recebi: {intent}"
        assert payload.get("calendar_action") is None

    def test_tarefa_explicita_vai_para_tarefa(self, monkeypatch):
        """'criar tarefa: entregar trabalho amanhã' → tarefa (não calendário)."""

        def _fake_orchestrate(msg, uid, db):
            return {
                "answer": "✅ Tarefa criada: **Entregar trabalho amanhã**",
                "intent": "create_task",
            }

        monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", _fake_orchestrate)

        client = _make_auth_client()
        resp = client.post("/api/chat", json={
            "message": "criar tarefa: entregar trabalho amanhã"
        })
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        intent = payload.get("intent", "")
        assert "task" in intent or "tarefa" in intent or "create_task" in intent, \
            f"Esperava intent de tarefa, recebi: {intent}"
        assert payload.get("calendar_action") is None


# ── Regressão: plano de estudos ───────────────────────────────────────────────


class TestStudyPlanRegression:
    """Garante que o fluxo de plano de estudos não quebrou."""

    def test_study_plan_intent_still_handled_by_orchestrator(self, monkeypatch):
        """'quero criar um plano de estudos' → orchestrator retorna cascade_study_plan."""

        study_plan_triggered = {}

        def _fake_orchestrate(msg, uid, db):
            study_plan_triggered["called"] = True
            return {
                "answer": (
                    "📚 Plano de estudos criado para **Aula.pdf**!\n"
                    "✅ 4 tarefas por tópico criadas\n"
                    "📅 4 sessões de estudo no calendário"
                ),
                "intent": "cascade_study_plan",
            }

        monkeypatch.setattr("docops.services.orchestrator.maybe_orchestrate", _fake_orchestrate)

        client = _make_auth_client()
        resp = client.post("/api/chat", json={
            "message": "quero criar um plano de estudos para o documento aula com 1h por dia até dia 07/04"
        })
        _clear_auth()

        assert resp.status_code == 200
        payload = resp.json()
        assert study_plan_triggered.get("called") is True
        assert payload["intent"] == "cascade_study_plan"
        assert "plano" in payload["answer"].lower() or "estudo" in payload["answer"].lower()


# ── Testes unitários do orchestrator (sem HTTP) ────────────────────────────────


class TestOrchestratorCalendarPassthrough:
    """Testa diretamente o maybe_orchestrate para garantir pass-through correto."""

    def test_lembrete_returns_none_from_orchestrator(self, monkeypatch):
        """O orchestrator deve retornar None para 'lembrete' → deixa calendar_assistant agir."""
        from docops.services import orchestrator

        monkeypatch.setattr(orchestrator, "_llm_parse",
                            lambda msg: {"intent": "calendar", "entities": {}})

        db_mock = MagicMock()
        result = orchestrator.maybe_orchestrate(
            "criar um lembrete no calendário para as 14h", user_id=1, db=db_mock
        )
        assert result is None, "Orchestrator deve retornar None para intent=calendar"

    def test_calendar_correction_returns_none(self, monkeypatch):
        """Correção explícita 'não é nas notas, é no calendário' → orchestrator retorna None sem chamar LLM."""
        from docops.services import orchestrator

        llm_called = {}

        def _spy_llm(msg):
            llm_called["called"] = True
            return {"intent": "cascade_create_note", "entities": {}}

        monkeypatch.setattr(orchestrator, "_llm_parse", _spy_llm)

        db_mock = MagicMock()
        result = orchestrator.maybe_orchestrate(
            "não é nas notas, é no calendário", user_id=1, db=db_mock
        )
        assert result is None, "Correção explícita deve fazer pass-through"
        assert not llm_called.get("called"), "LLM não deve ser chamado para correção explícita"

    def test_rotina_semanal_returns_none_from_orchestrator(self, monkeypatch):
        """'criar minha rotina semanal' → orchestrator retorna None para calendar_assistant."""
        from docops.services import orchestrator

        monkeypatch.setattr(orchestrator, "_llm_parse",
                            lambda msg: {"intent": "calendar", "entities": {}})

        db_mock = MagicMock()
        result = orchestrator.maybe_orchestrate(
            "quero criar minha rotina semanal", user_id=1, db=db_mock
        )
        assert result is None, "Orchestrator deve retornar None para rotina/calendário"

    def test_nota_explicita_retorna_resposta(self, monkeypatch):
        """'anota isso: revisar cap 3' → orchestrator cria nota (não passa para calendário)."""
        from docops.services import orchestrator
        from docops.db import crud

        monkeypatch.setattr(orchestrator, "_llm_parse", lambda msg: {
            "intent": "cascade_create_note",
            "entities": {"content": "revisar cap 3", "topic": "revisar cap 3"},
        })

        mock_note = MagicMock()
        mock_note.id = 1
        monkeypatch.setattr(crud, "create_note_record", lambda *a, **kw: mock_note)

        db_mock = MagicMock()
        result = orchestrator.maybe_orchestrate(
            "anota isso: revisar cap 3", user_id=1, db=db_mock
        )

        assert result is not None, "Orchestrator deve tratar notas explícitas"
        assert "nota" in result.get("intent", "").lower() or "note" in result.get("intent", "").lower()

    def test_tarefa_simples_nao_vira_calendario(self, monkeypatch):
        """'criar tarefa: revisar código' → nunca deve virar intent de calendário."""
        from docops.services import orchestrator
        from docops.db import crud

        monkeypatch.setattr(orchestrator, "_llm_parse", lambda msg: {
            "intent": "create_task",
            "entities": {"task_title": "Revisar código"},
        })

        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.title = "Revisar código"
        monkeypatch.setattr(crud, "create_task_record", lambda *a, **kw: mock_task)

        db_mock = MagicMock()
        result = orchestrator.maybe_orchestrate(
            "criar tarefa: revisar código", user_id=1, db=db_mock
        )

        # Pode retornar None (regex não pegou) ou resposta de tarefa — nunca calendário
        if result is not None:
            assert "calendar" not in result.get("intent", ""), \
                "Tarefa não deve virar intent de calendário"
