"""Tests for the retriever and citations — uses mocks to avoid API calls."""

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from docops.rag.citations import (
    build_context_block,
    build_sources_section,
    count_citations_in_answer,
    _snippet,
    _context_text,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_chunk(text: str, file_name: str = "doc.pdf", page: int = 1) -> Document:
    return Document(
        page_content=text,
        metadata={
            "file_name": file_name,
            "source": f"docs/{file_name}",
            "page": page,
            "chunk_id": "abc123",
        },
    )


# ── Citation/context building tests ─────────────────────────────────────────

def test_build_context_block_empty():
    result = build_context_block([])
    assert "Nenhum trecho" in result


def test_build_context_block_single_chunk():
    chunk = _make_chunk("This is the document content.", file_name="manual.pdf", page=2)
    result = build_context_block([chunk])
    assert "[Fonte 1]" in result
    assert "manual.pdf" in result
    assert "página 2" in result


def test_build_context_block_multiple_chunks():
    chunks = [
        _make_chunk("First chunk content.", file_name="a.pdf", page=1),
        _make_chunk("Second chunk content.", file_name="b.pdf", page=5),
    ]
    result = build_context_block(chunks)
    assert "[Fonte 1]" in result
    assert "[Fonte 2]" in result
    assert "a.pdf" in result
    assert "b.pdf" in result


def test_build_context_block_contains_full_text():
    """Improvement A: context block should contain the FULL chunk text, not just a snippet."""
    long_text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
        "nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in "
        "reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla "
        "pariatur. MIDDLE_MARKER_TEXT_UNIQUE. Excepteur sint occaecat cupidatat "
        "non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
    )
    chunk = _make_chunk(long_text, file_name="paper.pdf", page=3)
    result = build_context_block([chunk])

    # The marker text in the middle of the chunk should appear in the context
    assert "MIDDLE_MARKER_TEXT_UNIQUE" in result
    # Should still have source header
    assert "[Fonte 1]" in result
    assert "paper.pdf" in result


def test_build_context_block_text_vs_snippet():
    """Context block should contain much more text than the old 120-char snippet."""
    text = "word " * 100  # 500 chars
    chunk = _make_chunk(text.strip())

    context = build_context_block([chunk])
    # Context should contain the full text (500 chars), not truncated to 120
    snippet_result = _snippet(text, max_chars=120)
    assert len(context) > len(snippet_result)


def test_build_sources_section():
    chunk = _make_chunk("Important paragraph here.", file_name="thesis.pdf", page=10)
    result = build_sources_section([chunk])
    assert "**Fontes:**" in result
    assert "thesis.pdf" in result
    assert "p. 10" in result


def test_build_sources_section_no_page():
    chunk = Document(
        page_content="Markdown content here.",
        metadata={
            "file_name": "notes.md",
            "source": "docs/notes.md",
            "page": "N/A",
            "chunk_id": "xyz",
        },
    )
    result = build_sources_section([chunk])
    assert "notes.md" in result
    assert "N/A" not in result  # Page N/A should not appear in output


def test_build_sources_section_uses_short_snippet():
    """Sources section should still use short snippets, not full text."""
    long_text = "word " * 100  # 500 chars
    chunk = _make_chunk(long_text.strip(), file_name="big.pdf", page=1)
    result = build_sources_section([chunk])
    # Sources section should be much shorter than the full text
    assert len(result) < len(long_text)


def test_count_citations_in_answer_zero():
    answer = "This is a plain answer without any citations."
    assert count_citations_in_answer(answer) == 0


def test_count_citations_in_answer_multiple():
    answer = "As stated [Fonte 1], confirmed [Fonte 2], and also [Fonte 3]."
    assert count_citations_in_answer(answer) == 3


def test_count_citations_case_insensitive():
    answer = "See [fonte 1] and [FONTE 2]."
    assert count_citations_in_answer(answer) == 2


def test_snippet_short_text():
    text = "Short text."
    result = _snippet(text, max_chars=120)
    assert result == "Short text."


def test_snippet_truncation():
    text = "word " * 100  # 500 chars
    result = _snippet(text, max_chars=50)
    assert len(result) <= 55  # slight tolerance for ellipsis
    assert result.endswith("…")


def test_snippet_strips_newlines():
    text = "Line one.\nLine two.\nLine three."
    result = _snippet(text)
    assert "\n" not in result


# ── _context_text tests ──────────────────────────────────────────────────────

def test_context_text_short_text():
    """Short text should be returned as-is."""
    text = "Short."
    result = _context_text(text, max_chars=1500)
    assert result == "Short."


def test_context_text_truncation():
    """Long text should be truncated at the configured limit."""
    text = "x " * 1000  # 2000 chars
    result = _context_text(text, max_chars=200)
    assert len(result) <= 210  # tolerance for word boundary + ellipsis
    assert result.endswith("…")


def test_context_text_no_limit():
    """max_chars=0 should return full text."""
    text = "x " * 1000
    result = _context_text(text, max_chars=0)
    assert result == text.strip()


# ── Retriever mock tests — score threshold ───────────────────────────────────

def test_retrieve_similarity_with_scores():
    """Improvement B: similarity mode should use score-based retrieval."""
    chunk1 = _make_chunk("High relevance content")
    chunk2 = _make_chunk("Low relevance content")

    mock_vectorstore = MagicMock()
    mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
        (chunk1, 0.85),
        (chunk2, 0.10),  # Below default threshold of 0.2
    ]

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.2
        mock_config.retrieval_mode = "similarity"
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("test query", top_k=2)

    # Only the high-score chunk should pass the threshold
    assert len(results) == 1
    assert results[0].page_content == "High relevance content"
    assert results[0].metadata["retrieval_score"] == 0.85


def test_retrieve_returns_empty_when_all_below_threshold():
    """When all scores are below threshold, return empty list."""
    chunk = _make_chunk("Weak content")

    mock_vectorstore = MagicMock()
    mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
        (chunk, 0.05),
    ]

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.2
        mock_config.retrieval_mode = "similarity"
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("test query")

    assert results == []


def test_retrieve_score_attached_to_metadata():
    """Score should be attached to Document.metadata as retrieval_score."""
    chunk = _make_chunk("Good content")

    mock_vectorstore = MagicMock()
    mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
        (chunk, 0.9123),
    ]

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.0
        mock_config.retrieval_mode = "similarity"
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("test query")

    assert results[0].metadata["retrieval_score"] == 0.9123


# ── Retriever mock tests — MMR ──────────────────────────────────────────────

def test_retrieve_mmr_calls_max_marginal_relevance_search():
    """Improvement C: MMR mode should call max_marginal_relevance_search."""
    chunk1 = _make_chunk("MMR result 1")
    chunk2 = _make_chunk("MMR result 2")
    gate_chunk = _make_chunk("Gate check")

    mock_vectorstore = MagicMock()
    # Gate check passes
    mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
        (gate_chunk, 0.8),
    ]
    # MMR returns results
    mock_vectorstore.max_marginal_relevance_search.return_value = [chunk1, chunk2]

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.2
        mock_config.retrieval_mode = "mmr"
        mock_config.mmr_fetch_k = 24
        mock_config.mmr_lambda = 0.5
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("test query", top_k=2)

    # Verify MMR was called
    mock_vectorstore.max_marginal_relevance_search.assert_called_once_with(
        "test query", k=2, fetch_k=24, lambda_mult=0.5
    )
    assert len(results) == 2
    assert results[0].metadata.get("retrieval_mode") == "mmr"


def test_retrieve_mmr_gated_when_score_low():
    """MMR mode should return [] when the score gate fails."""
    gate_chunk = _make_chunk("Weak content")

    mock_vectorstore = MagicMock()
    # Gate check fails — best score below threshold
    mock_vectorstore.similarity_search_with_relevance_scores.return_value = [
        (gate_chunk, 0.05),
    ]

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.2
        mock_config.retrieval_mode = "mmr"
        mock_config.mmr_fetch_k = 24
        mock_config.mmr_lambda = 0.5
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("test query")

    assert results == []
    # MMR should NOT be called when gate fails
    mock_vectorstore.max_marginal_relevance_search.assert_not_called()


def test_retrieve_mmr_fallback_to_similarity():
    """MMR should fall back to similarity search if MMR is not available."""
    chunk = _make_chunk("Fallback content")
    gate_chunk = _make_chunk("Gate check")

    mock_vectorstore = MagicMock()
    # MMR not available
    mock_vectorstore.max_marginal_relevance_search.side_effect = NotImplementedError

    # similarity_search_with_relevance_scores is called twice:
    # 1. Gate check (passes)
    # 2. Fallback similarity search
    mock_vectorstore.similarity_search_with_relevance_scores.side_effect = [
        [(gate_chunk, 0.8)],       # Gate check
        [(chunk, 0.75)],           # Fallback similarity search
    ]

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.2
        mock_config.retrieval_mode = "mmr"
        mock_config.mmr_fetch_k = 24
        mock_config.mmr_lambda = 0.5
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("test query", top_k=2)

    assert len(results) == 1
    assert results[0].page_content == "Fallback content"


# ── Legacy compatibility tests ───────────────────────────────────────────────

def test_retrieve_handles_exception_gracefully():
    """Retriever should return empty list on vectorstore errors."""
    mock_vectorstore = MagicMock()
    mock_vectorstore.similarity_search_with_relevance_scores.side_effect = Exception("DB error")

    with (
        patch("docops.rag.retriever._get_vs", return_value=mock_vectorstore),
        patch("docops.rag.retriever.config") as mock_config,
    ):
        mock_config.top_k = 6
        mock_config.min_relevance_score = 0.2
        mock_config.retrieval_mode = "similarity"
        mock_config.multi_query = False
        mock_config.reranker = "none"

        from docops.rag.retriever import retrieve
        results = retrieve("query", top_k=5)

    assert results == []


class FakeEmbeddings:
    """Deterministic fake embeddings for Chroma integration tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 10) / 10.0] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 8


def _make_index_chunk(text: str, source_path: str) -> Document:
    file_name = Path(source_path).name
    return Document(
        page_content=text,
        metadata={
            "file_name": file_name,
            "source_path": source_path,
            "source": source_path,
        },
    )


def _make_test_config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        chroma_dir=root / "chroma",
        bm25_dir=root / "bm25",
        docs_dir=root / "docs",
        artifacts_dir=root / "artifacts",
        uploads_dir=root / "uploads",
        ingest_incremental=False,
        top_k=6,
        hybrid_k_lex=6,
    )


def test_reingest_replaces_stale_chunks_and_keeps_hybrid_consistent():
    from docops.ingestion.indexer import get_vectorstore_for_user, index_chunks_for_user
    from docops.ingestion.metadata import build_doc_id
    from docops.rag.hybrid import bm25_search_for_user, hybrid_retrieve_for_user

    fake_emb = FakeEmbeddings()
    user_id = 42
    source_path = "docs/manual.md"
    doc_id = build_doc_id(source_path, user_id=user_id)

    tmpdir = tempfile.mkdtemp()
    try:
        cfg = _make_test_config(Path(tmpdir))
        with (
            patch("docops.ingestion.indexer.config", cfg),
            patch("docops.rag.hybrid.config", cfg),
            patch("docops.storage.paths.config", cfg),
        ):
            chunks_v1 = [_make_index_chunk("token_v1_exclusivo conteudo antigo", source_path)]
            chunks_v2 = [_make_index_chunk("token_v2_exclusivo conteudo novo", source_path)]

            indexed_v1 = index_chunks_for_user(user_id=user_id, chunks=chunks_v1, embeddings=fake_emb)
            assert indexed_v1 == 1
            assert bm25_search_for_user(user_id, "token_v1_exclusivo", k=5)

            indexed_v2 = index_chunks_for_user(user_id=user_id, chunks=chunks_v2, embeddings=fake_emb)
            assert indexed_v2 == 1

            vs = get_vectorstore_for_user(user_id=user_id, embeddings=fake_emb)
            stored = vs._collection.get(where={"doc_id": doc_id}, include=["documents"])
            docs = stored.get("documents", [])
            assert docs
            assert all("token_v1_exclusivo" not in text for text in docs)
            assert any("token_v2_exclusivo" in text for text in docs)

            bm25_old = bm25_search_for_user(user_id, "token_v1_exclusivo", k=5)
            assert not any("token_v1_exclusivo" in d.page_content for d in bm25_old)

            hybrid_old = hybrid_retrieve_for_user(
                user_id=user_id,
                query="token_v1_exclusivo",
                vector_fn=lambda q, k: vs.similarity_search(q, k=k),
                k_vec=5,
                k_lex=5,
            )
            assert not any("token_v1_exclusivo" in d.page_content for d in hybrid_old)
            del vs
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_ingesting_second_doc_preserves_first_doc_in_bm25():
    from docops.ingestion.indexer import index_chunks_for_user
    from docops.rag.hybrid import bm25_search_for_user

    fake_emb = FakeEmbeddings()
    user_id = 91

    tmpdir = tempfile.mkdtemp()
    try:
        cfg = _make_test_config(Path(tmpdir))
        with (
            patch("docops.ingestion.indexer.config", cfg),
            patch("docops.rag.hybrid.config", cfg),
            patch("docops.storage.paths.config", cfg),
        ):
            chunk_a = _make_index_chunk("token_doc_a_exclusivo", "docs/a.md")
            chunk_b = _make_index_chunk("token_doc_b_exclusivo", "docs/b.md")

            assert index_chunks_for_user(user_id=user_id, chunks=[chunk_a], embeddings=fake_emb) == 1
            assert index_chunks_for_user(user_id=user_id, chunks=[chunk_b], embeddings=fake_emb) == 1

            results_a = bm25_search_for_user(user_id, "token_doc_a_exclusivo", k=10)
            results_b = bm25_search_for_user(user_id, "token_doc_b_exclusivo", k=10)

            assert any("token_doc_a_exclusivo" in d.page_content for d in results_a)
            assert any("token_doc_b_exclusivo" in d.page_content for d in results_b)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_delete_doc_removes_entries_from_vector_and_bm25():
    from docops.ingestion.indexer import delete_doc_from_index, get_vectorstore_for_user, index_chunks_for_user
    from docops.ingestion.metadata import build_doc_id
    from docops.rag.hybrid import bm25_search_for_user, hybrid_retrieve_for_user

    fake_emb = FakeEmbeddings()
    user_id = 77
    source_path = "docs/guide.md"
    doc_id = build_doc_id(source_path, user_id=user_id)

    tmpdir = tempfile.mkdtemp()
    try:
        cfg = _make_test_config(Path(tmpdir))
        with (
            patch("docops.ingestion.indexer.config", cfg),
            patch("docops.rag.hybrid.config", cfg),
            patch("docops.storage.paths.config", cfg),
        ):
            chunks = [_make_index_chunk("token_delete_exclusivo", source_path)]
            indexed = index_chunks_for_user(user_id=user_id, chunks=chunks, embeddings=fake_emb)
            assert indexed == 1
            assert bm25_search_for_user(user_id, "token_delete_exclusivo", k=5)

            deleted = delete_doc_from_index(doc_id=doc_id, user_id=user_id, embeddings=fake_emb)
            assert deleted >= 1

            vs = get_vectorstore_for_user(user_id=user_id, embeddings=fake_emb)
            payload = vs._collection.get(where={"doc_id": doc_id}, include=[])
            assert payload.get("ids", []) == []

            bm25_results = bm25_search_for_user(user_id, "token_delete_exclusivo", k=5)
            assert bm25_results == []

            hybrid_results = hybrid_retrieve_for_user(
                user_id=user_id,
                query="token_delete_exclusivo",
                vector_fn=lambda q, k: vs.similarity_search(q, k=k),
                k_vec=5,
                k_lex=5,
            )
            assert hybrid_results == []
            del vs
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
