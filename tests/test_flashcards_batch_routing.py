"""Testes do roteamento de flashcards em lote no chat."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from docops.db import crud
from docops.services import action_router, orchestrator


def _make_doc(file_name: str, doc_id: str) -> SimpleNamespace:
    return SimpleNamespace(file_name=file_name, doc_id=doc_id)


@pytest.fixture(autouse=True)
def _clear_pending_batches():
    orchestrator._pending_flashcard_batches.clear()
    yield
    orchestrator._pending_flashcard_batches.clear()


def test_create_flashcards_batch_for_all_docs(monkeypatch):
    docs = [
        _make_doc("Aula_1_-_Significado_de_aprendizagem.pdf", "doc-1"),
        _make_doc("Aula_2_-_Viabilidade_da_Aprendizagem.pdf", "doc-2"),
    ]
    created = []

    monkeypatch.setattr(
        orchestrator,
        "_llm_parse",
        lambda msg, history=None: {
            "intent": "create_task",
            "entities": {
                "all_docs": True,
                "doc_names": [],
                "num_cards": 10,
                "difficulty_mode": "custom",
                "difficulty_custom": {"facil": 5, "media": 3, "dificil": 2},
            },
        },
    )
    monkeypatch.setattr(crud, "list_documents_for_user", lambda db, user_id: docs)
    monkeypatch.setattr(
        "docops.api.routes.flashcards._generate_cards",
        lambda **kwargs: [{"front": f"{kwargs['doc_name']} Q{i}", "back": "A", "difficulty": "facil"} for i in range(10)],
    )

    def _create_deck(db, *, user_id, title, source_doc, cards):
        created.append((title, source_doc, len(cards)))
        return SimpleNamespace(id=len(created), title=title, source_doc=source_doc, cards=cards)

    monkeypatch.setattr(crud, "create_flashcard_deck", _create_deck)

    result = orchestrator.maybe_orchestrate(
        "quero que faça 10 flashcards sendo 5 fáceis, 3 médias e 2 difíceis para cada documento que tem na aba documentos",
        user_id=1,
        db=MagicMock(),
        history=[],
    )

    assert result is not None
    assert result["intent"] == "create_flashcards_batch"
    assert "2 deck(s)" in result["answer"]
    assert len(created) == 2
    assert created[0][1] == "Aula_1_-_Significado_de_aprendizagem.pdf"
    assert created[1][1] == "Aula_2_-_Viabilidade_da_Aprendizagem.pdf"


def test_flashcard_command_ambiguous_prompts_for_confirmation_not_task(monkeypatch):
    created_tasks = []

    monkeypatch.setattr(
        orchestrator,
        "_llm_parse",
        lambda msg, history=None: {"intent": "create_task", "entities": {}},
    )
    monkeypatch.setattr(crud, "list_documents_for_user", lambda db, user_id: [])
    monkeypatch.setattr(
        crud,
        "create_task_record",
        lambda *args, **kwargs: created_tasks.append((args, kwargs)),
    )

    result = orchestrator.maybe_orchestrate(
        "quero que crie os flashcards",
        user_id=1,
        db=MagicMock(),
        history=[],
    )

    assert result is not None
    assert result["intent"] == "create_flashcards_batch"
    assert result.get("needs_confirmation") is True
    assert "documento" in result["answer"].lower()
    assert not created_tasks
    assert 1 in orchestrator._pending_flashcard_batches


def test_flashcard_command_does_not_create_task(monkeypatch):
    task_calls = []

    monkeypatch.setattr(
        orchestrator,
        "_llm_parse",
        lambda msg, history=None: {"intent": "create_task", "entities": {"task_title": "Criar flashcards"}},
    )
    monkeypatch.setattr(crud, "list_documents_for_user", lambda db, user_id: [])
    monkeypatch.setattr(
        crud,
        "create_task_record",
        lambda *args, **kwargs: task_calls.append((args, kwargs)),
    )

    result = orchestrator.maybe_orchestrate(
        "quero que faça 10 flashcards",
        user_id=2,
        db=MagicMock(),
        history=[],
    )

    assert result is not None
    assert result["intent"] in {"create_flashcards_batch", "clarification_needed"}
    assert not task_calls


def test_action_router_leaves_flashcard_commands_for_orchestrator():
    result = action_router.maybe_answer_action_query(
        "quero que faça 10 flashcards sendo 5 fáceis, 3 médias e 2 difíceis para cada documento",
        user_id=1,
        db=MagicMock(),
    )

    assert result is None
