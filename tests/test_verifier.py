"""Tests for the grounding verifier."""

import pytest
from langchain_core.documents import Document

from docops.rag.verifier import (
    is_factual_answer,
    has_min_citations,
    verify_grounding,
)
from docops.graph.state import AgentState


def _make_chunk(text: str = "Sample content.") -> Document:
    return Document(
        page_content=text,
        metadata={"file_name": "doc.pdf", "page": 1, "chunk_id": "abc"},
    )


# ── is_factual_answer ─────────────────────────────────────────────────────────

def test_factual_year():
    assert is_factual_answer("This happened in 2023 according to studies.") is True


def test_factual_percentage():
    assert is_factual_answer("The result was 87.5% improvement.") is True


def test_factual_definition():
    assert is_factual_answer("RAG define-se como retrieval-augmented generation.") is True


def test_non_factual_answer():
    assert is_factual_answer("Não encontrei informações suficientes nos documentos.") is False


def test_non_factual_short():
    assert is_factual_answer("Ok, entendido.") is False


# ── has_min_citations ─────────────────────────────────────────────────────────

def test_has_min_citations_enough():
    answer = "First claim [Fonte 1]. Second claim [Fonte 2]."
    assert has_min_citations(answer, min_cites=2) is True


def test_has_min_citations_not_enough():
    answer = "Single citation [Fonte 1] but needs more."
    assert has_min_citations(answer, min_cites=2) is False


def test_has_min_citations_zero_required():
    answer = "No citations needed."
    assert has_min_citations(answer, min_cites=0) is True


def test_has_min_citations_exact():
    answer = "[Fonte 1] and [Fonte 2]."
    assert has_min_citations(answer, min_cites=2) is True
    assert has_min_citations(answer, min_cites=3) is False


# ── verify_grounding ──────────────────────────────────────────────────────────

def test_verify_grounding_no_chunks_fails():
    state: AgentState = {
        "query": "test",
        "answer": "Some factual answer from 2023.",
        "retrieved_chunks": [],
        "retry_count": 0,
    }
    result = verify_grounding(state)
    assert result["grounding_ok"] is False
    assert "Aviso" in result["disclaimer"]


def test_verify_grounding_non_factual_passes():
    state: AgentState = {
        "query": "test",
        "answer": "Não encontrei informação suficiente nos documentos.",
        "retrieved_chunks": [_make_chunk()],
        "retry_count": 0,
    }
    result = verify_grounding(state)
    assert result["grounding_ok"] is True
    assert result["retry"] is False


def test_verify_grounding_factual_with_citations_passes():
    state: AgentState = {
        "query": "test",
        "answer": "Em 2023 [Fonte 1], o resultado foi 85% [Fonte 2].",
        "retrieved_chunks": [_make_chunk(), _make_chunk()],
        "retry_count": 0,
    }
    result = verify_grounding(state)
    assert result["grounding_ok"] is True


def test_verify_grounding_factual_no_citations_triggers_retry():
    state: AgentState = {
        "query": "test",
        "answer": "Em 2023, o resultado foi 85%.",  # factual, no citations
        "retrieved_chunks": [_make_chunk()],
        "retry_count": 0,
    }
    result = verify_grounding(state)
    assert result["grounding_ok"] is False
    assert result["retry"] is True


def test_verify_grounding_max_retries_exhausted_adds_disclaimer():
    state: AgentState = {
        "query": "test",
        "answer": "Em 2023, o resultado foi 85%.",  # factual, no citations
        "retrieved_chunks": [_make_chunk()],
        "retry_count": 99,  # Way over max_retries
    }
    result = verify_grounding(state)
    assert result["grounding_ok"] is False
    assert result["retry"] is False
    assert "Aviso" in result["disclaimer"]


def test_verify_grounding_retry_increments():
    """After max retries, should not retry further."""
    from docops.config import config

    state: AgentState = {
        "query": "test",
        "answer": "Data de 2022 mostra que 90% dos casos.",
        "retrieved_chunks": [_make_chunk()],
        "retry_count": config.max_retries,  # At max
    }
    result = verify_grounding(state)
    assert result["retry"] is False
