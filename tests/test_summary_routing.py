"""Tests for summary routing behavior in orchestrator."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from docops.services import orchestrator


def test_deep_summary_recommends_artifact_flow(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_llm_parse",
        lambda msg, history=None, active_context=None: {
            "intent": "cascade_create_summary",
            "entities": {"doc_hint": "manual_ml.pdf"},
        },
    )

    result = orchestrator.maybe_orchestrate(
        "me faca um resumo aprofundado desse documento",
        user_id=1,
        db=MagicMock(),
        history=[],
    )

    assert result is not None
    assert result["intent"] == "cascade_create_summary"
    assert "/artifacts" in result["answer"]
    assert "Resumo Aprofundado" in result["answer"]
    assert "Resumo Breve" in result["answer"]
    assert "direto aqui no chat" in result["answer"]


def test_brief_summary_passes_through_to_chat_rag(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_llm_parse",
        lambda msg, history=None, active_context=None: {
            "intent": "cascade_create_summary",
            "entities": {"doc_hint": "manual_ml.pdf"},
        },
    )

    result = orchestrator.maybe_orchestrate(
        "me faca um resumo breve desse documento",
        user_id=1,
        db=MagicMock(),
        history=[],
    )

    assert result is None


def test_generic_summary_passes_through_to_chat_rag(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_llm_parse",
        lambda msg, history=None, active_context=None: {
            "intent": "cascade_create_summary",
            "entities": {"doc_hint": "manual_ml.pdf"},
        },
    )

    result = orchestrator.maybe_orchestrate(
        "me faca um resumo desse documento",
        user_id=1,
        db=MagicMock(),
        history=[],
    )

    assert result is None
