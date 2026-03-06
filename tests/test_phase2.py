"""Tests for Phase 2 RAG improvements.

Covers:
  2.1 Query rewriting + Multi-query retrieval
  2.2 Reranking (local + llm)
  2.3 Hybrid search (BM25 + vector RRF)
  2.4 Stable IDs + incremental ingest
  2.5 Citation improvements (evidence snippet, chunk_id in sources)
  2.6 Better verifier (phantom citations, max_citation_index)

No real Gemini API calls — all LLM interactions are mocked.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


# ═══════════════════════════════════════════════════════════════════════════════
# 2.1 — Query rewriting + Multi-query retrieval
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueryRewrite:
    def test_rewrite_queries_returns_variations(self):
        from docops.rag.query_rewrite import rewrite_queries

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="O que é aprendizado de máquina?\nComo funciona machine learning?\nExplique ML"
        )

        result = rewrite_queries("O que é ML?", mock_llm, n=3)
        assert len(result) == 3
        assert all(isinstance(q, str) for q in result)
        mock_llm.invoke.assert_called_once()

    def test_rewrite_queries_handles_llm_failure(self):
        from docops.rag.query_rewrite import rewrite_queries

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API error")

        result = rewrite_queries("test query", mock_llm, n=3)
        assert result == []

    def test_rewrite_queries_excludes_original(self):
        from docops.rag.query_rewrite import rewrite_queries

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="test query\nvariation one\nvariation two"
        )

        result = rewrite_queries("test query", mock_llm, n=3)
        assert "test query" not in [q.lower() for q in result]

    def test_rewrite_queries_respects_n_limit(self):
        from docops.rag.query_rewrite import rewrite_queries

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="v1\nv2\nv3\nv4\nv5"
        )

        result = rewrite_queries("q", mock_llm, n=2)
        assert len(result) <= 2

    def test_multi_query_retrieve_deduplicates(self):
        from docops.rag.query_rewrite import multi_query_retrieve

        doc_a = Document(page_content="text A", metadata={"chunk_id": "aaa"})
        doc_b = Document(page_content="text B", metadata={"chunk_id": "bbb"})
        doc_a_dup = Document(page_content="text A", metadata={"chunk_id": "aaa"})

        call_count = [0]

        def fake_retrieve(q, k):
            call_count[0] += 1
            if call_count[0] == 1:
                return [doc_a, doc_b]
            return [doc_a_dup]

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="variation 1")

        result = multi_query_retrieve("q", fake_retrieve, mock_llm, n_variations=1)
        chunk_ids = [d.metadata["chunk_id"] for d in result]
        assert chunk_ids == ["aaa", "bbb"]  # no dups

    def test_multi_query_retrieve_keeps_no_id_docs(self):
        from docops.rag.query_rewrite import multi_query_retrieve

        doc_no_id = Document(page_content="no id", metadata={})

        def fake_retrieve(q, k):
            return [doc_no_id]

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="variation")

        result = multi_query_retrieve("q", fake_retrieve, mock_llm, n_variations=1)
        assert len(result) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2 — Reranking
# ═══════════════════════════════════════════════════════════════════════════════

class TestReranking:
    def _make_docs(self):
        return [
            Document(
                page_content="Python é uma linguagem de programação popular",
                metadata={"retrieval_score": 0.9},
            ),
            Document(
                page_content="Java é usada em sistemas corporativos",
                metadata={"retrieval_score": 0.5},
            ),
            Document(
                page_content="Python para ciência de dados e machine learning",
                metadata={"retrieval_score": 0.7},
            ),
        ]

    def test_rerank_local_sorts_by_combined_score(self):
        from docops.rag.reranker import rerank_local

        docs = self._make_docs()
        result = rerank_local("Python programação", docs)

        assert len(result) == 3
        # All should have rerank_score
        assert all("rerank_score" in d.metadata for d in result)
        # Should be sorted descending
        scores = [d.metadata["rerank_score"] for d in result]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_local_top_n(self):
        from docops.rag.reranker import rerank_local

        docs = self._make_docs()
        result = rerank_local("Python", docs, top_n=2)
        assert len(result) == 2

    def test_rerank_llm_calls_llm_per_doc(self):
        from docops.rag.reranker import rerank_llm

        docs = self._make_docs()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="0.8")

        result = rerank_llm("Python", docs, mock_llm)
        assert mock_llm.invoke.call_count == 3
        assert len(result) == 3

    def test_rerank_llm_handles_bad_score(self):
        from docops.rag.reranker import rerank_llm

        docs = [Document(page_content="text", metadata={})]
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="not a number")

        result = rerank_llm("q", docs, mock_llm)
        assert result[0].metadata["rerank_score"] == 0.5  # fallback

    def test_rerank_llm_top_n(self):
        from docops.rag.reranker import rerank_llm

        docs = self._make_docs()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="0.7")

        result = rerank_llm("q", docs, mock_llm, top_n=1)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2.3 — Hybrid search (BM25 + vector RRF)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHybridSearch:
    def test_build_bm25_index_creates_files(self):
        from docops.rag.hybrid import build_bm25_index, _bm25_path, _corpus_path

        chunks = [
            Document(page_content="Python programming language", metadata={"chunk_id": "c1"}),
            Document(page_content="Java enterprise systems", metadata={"chunk_id": "c2"}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("docops.rag.hybrid.config") as mock_cfg:
                mock_cfg.bm25_dir = Path(tmpdir)
                # Patch _bm25_path and _corpus_path
                with patch("docops.rag.hybrid._bm25_path", return_value=Path(tmpdir) / "bm25_index.pkl"), \
                     patch("docops.rag.hybrid._corpus_path", return_value=Path(tmpdir) / "bm25_index.json"):
                    build_bm25_index(chunks)

                    assert (Path(tmpdir) / "bm25_index.pkl").exists()
                    assert (Path(tmpdir) / "bm25_index.json").exists()

    def test_bm25_search_returns_docs(self):
        from docops.rag.hybrid import build_bm25_index, bm25_search

        chunks = [
            Document(page_content="Python is great for data science", metadata={"chunk_id": "c1"}),
            Document(page_content="Java is used in enterprise", metadata={"chunk_id": "c2"}),
            Document(page_content="Python machine learning frameworks", metadata={"chunk_id": "c3"}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            idx_path = Path(tmpdir) / "bm25_index.pkl"
            corp_path = Path(tmpdir) / "bm25_index.json"

            with patch("docops.rag.hybrid._bm25_path", return_value=idx_path), \
                 patch("docops.rag.hybrid._corpus_path", return_value=corp_path), \
                 patch("docops.rag.hybrid.config") as mock_cfg:
                mock_cfg.bm25_dir = Path(tmpdir)

                build_bm25_index(chunks)
                results = bm25_search("Python data", k=2)

                assert len(results) == 2
                assert all("bm25_score" in d.metadata for d in results)

    def test_reciprocal_rank_fusion_merges(self):
        from docops.rag.hybrid import reciprocal_rank_fusion

        list1 = [
            Document(page_content="A", metadata={"chunk_id": "a"}),
            Document(page_content="B", metadata={"chunk_id": "b"}),
        ]
        list2 = [
            Document(page_content="B", metadata={"chunk_id": "b"}),
            Document(page_content="C", metadata={"chunk_id": "c"}),
        ]

        result = reciprocal_rank_fusion([list1, list2])
        chunk_ids = [d.metadata["chunk_id"] for d in result]

        # B should be ranked highest (appears in both lists)
        assert chunk_ids[0] == "b"
        # All 3 unique docs present
        assert set(chunk_ids) == {"a", "b", "c"}

    def test_reciprocal_rank_fusion_empty_lists(self):
        from docops.rag.hybrid import reciprocal_rank_fusion

        result = reciprocal_rank_fusion([[], []])
        assert result == []

    def test_bm25_search_no_index(self):
        from docops.rag.hybrid import bm25_search

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("docops.rag.hybrid._bm25_path", return_value=Path(tmpdir) / "nonexistent.pkl"), \
                 patch("docops.rag.hybrid._corpus_path", return_value=Path(tmpdir) / "nonexistent.json"):
                results = bm25_search("test query")
                assert results == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2.4 — Stable IDs + incremental ingest
# ═══════════════════════════════════════════════════════════════════════════════

class TestStableIDs:
    def test_stable_chunk_id_deterministic(self):
        from docops.ingestion.splitter import _stable_chunk_id

        id1 = _stable_chunk_id("test.pdf", 0, "hello world")
        id2 = _stable_chunk_id("test.pdf", 0, "hello world")
        assert id1 == id2

    def test_stable_chunk_id_varies_with_content(self):
        from docops.ingestion.splitter import _stable_chunk_id

        id1 = _stable_chunk_id("test.pdf", 0, "hello world")
        id2 = _stable_chunk_id("test.pdf", 0, "different text")
        assert id1 != id2

    def test_stable_chunk_id_varies_with_index(self):
        from docops.ingestion.splitter import _stable_chunk_id

        id1 = _stable_chunk_id("test.pdf", 0, "hello")
        id2 = _stable_chunk_id("test.pdf", 1, "hello")
        assert id1 != id2

    def test_split_documents_stable_ids(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="A " * 500,
            metadata={"file_name": "test.md", "source": "/test.md"},
        )

        chunks1 = split_documents([doc], chunk_size=100, chunk_overlap=10, stable_ids=True)
        chunks2 = split_documents([doc], chunk_size=100, chunk_overlap=10, stable_ids=True)

        ids1 = [c.metadata["chunk_id"] for c in chunks1]
        ids2 = [c.metadata["chunk_id"] for c in chunks2]
        assert ids1 == ids2

    def test_split_documents_uuid_fallback(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="A " * 500,
            metadata={"file_name": "test.md", "source": "/test.md"},
        )

        chunks1 = split_documents([doc], chunk_size=100, chunk_overlap=10, stable_ids=False)
        chunks2 = split_documents([doc], chunk_size=100, chunk_overlap=10, stable_ids=False)

        ids1 = [c.metadata["chunk_id"] for c in chunks1]
        ids2 = [c.metadata["chunk_id"] for c in chunks2]
        # UUIDs should differ between runs
        assert ids1 != ids2


class TestIncrementalIngest:
    def test_incremental_skips_existing_chunks(self):
        from docops.ingestion.indexer import index_chunks, _load_manifest, _save_manifest, _manifest_path

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_file = Path(tmpdir) / "manifest.json"

            mock_vs = MagicMock()

            with patch("docops.ingestion.indexer.get_vectorstore", return_value=mock_vs), \
                 patch("docops.ingestion.indexer._manifest_path", return_value=manifest_file), \
                 patch("docops.ingestion.indexer.config") as mock_cfg:
                mock_cfg.ingest_incremental = True
                mock_cfg.chroma_dir = Path(tmpdir)

                # First ingest
                chunks = [
                    Document(page_content="text1", metadata={"chunk_id": "id1", "file_name": "a.md"}),
                    Document(page_content="text2", metadata={"chunk_id": "id2", "file_name": "a.md"}),
                ]
                count = index_chunks(chunks, incremental=True)
                assert count == 2
                mock_vs.add_documents.assert_called_once()

                # Second ingest with same IDs
                mock_vs.reset_mock()
                count2 = index_chunks(chunks, incremental=True)
                assert count2 == 0  # all skipped
                mock_vs.add_documents.assert_not_called()

    def test_incremental_indexes_new_chunks(self):
        from docops.ingestion.indexer import index_chunks, _manifest_path

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_file = Path(tmpdir) / "manifest.json"
            mock_vs = MagicMock()

            with patch("docops.ingestion.indexer.get_vectorstore", return_value=mock_vs), \
                 patch("docops.ingestion.indexer._manifest_path", return_value=manifest_file), \
                 patch("docops.ingestion.indexer.config") as mock_cfg:
                mock_cfg.ingest_incremental = True
                mock_cfg.chroma_dir = Path(tmpdir)

                # First batch
                chunks1 = [
                    Document(page_content="text1", metadata={"chunk_id": "id1", "file_name": "a.md"}),
                ]
                index_chunks(chunks1, incremental=True)

                # Second batch with 1 new + 1 existing
                mock_vs.reset_mock()
                chunks2 = [
                    Document(page_content="text1", metadata={"chunk_id": "id1", "file_name": "a.md"}),
                    Document(page_content="text3", metadata={"chunk_id": "id3", "file_name": "b.md"}),
                ]
                count = index_chunks(chunks2, incremental=True)
                assert count == 1  # only id3


# ═══════════════════════════════════════════════════════════════════════════════
# 2.5 — Citation improvements
# ═══════════════════════════════════════════════════════════════════════════════

class TestCitationImprovements:
    def test_extract_evidence_snippet_finds_relevant_region(self):
        from docops.rag.citations import extract_evidence_snippet

        text = (
            "Introduction to computing. "
            "Python is a popular programming language for data science. "
            "It was created by Guido van Rossum. "
            "The language emphasizes readability."
        )

        snippet = extract_evidence_snippet(text, "Python programming language")
        assert "Python" in snippet or "programming" in snippet

    def test_extract_evidence_snippet_empty_query(self):
        from docops.rag.citations import extract_evidence_snippet

        text = "Some text content here"
        snippet = extract_evidence_snippet(text, "")
        assert snippet  # falls back to _snippet

    def test_extract_evidence_snippet_empty_text(self):
        from docops.rag.citations import extract_evidence_snippet

        snippet = extract_evidence_snippet("", "query")
        assert snippet == ""

    def test_build_sources_section_includes_chunk_id(self):
        from docops.rag.citations import build_sources_section

        chunks = [
            Document(
                page_content="some text about Python",
                metadata={"file_name": "test.pdf", "page": 1, "chunk_id": "abcdef1234567890"},
            ),
        ]

        result = build_sources_section(chunks)
        assert "abcdef12" in result  # chunk_id[:8]

    def test_build_sources_section_with_query_uses_evidence(self):
        from docops.rag.citations import build_sources_section

        chunks = [
            Document(
                page_content="Introduction. Python is great for data science and machine learning applications.",
                metadata={"file_name": "ml.pdf", "page": 5, "chunk_id": "abc123"},
            ),
        ]

        result = build_sources_section(chunks, query="Python data science")
        assert "Fonte 1" in result

    def test_max_citation_index(self):
        from docops.rag.citations import max_citation_index

        assert max_citation_index("Segundo [Fonte 1] e [Fonte 3]") == 3
        assert max_citation_index("Sem citações") == 0
        assert max_citation_index("[Fonte 10] diz que") == 10


# ═══════════════════════════════════════════════════════════════════════════════
# 2.6 — Better verifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestBetterVerifier:
    def test_phantom_citation_detected(self):
        from docops.rag.verifier import verify_grounding

        state = {
            "answer": "Segundo [Fonte 1] e [Fonte 5], o resultado é 42%",
            "retry_count": 0,
            "retrieved_chunks": [
                Document(page_content="chunk 1", metadata={}),
                Document(page_content="chunk 2", metadata={}),
            ],
        }

        with patch("docops.rag.verifier.config") as mock_cfg:
            mock_cfg.min_citations = 2
            mock_cfg.max_retries = 2

            result = verify_grounding(state)
            # [Fonte 5] but only 2 chunks → should fail
            assert result["grounding_ok"] is False
            assert result["retry"] is True

    def test_phantom_citation_max_retries_exhausted(self):
        from docops.rag.verifier import verify_grounding

        state = {
            "answer": "Segundo [Fonte 9], isso é verdade em 2023",
            "retry_count": 3,
            "retrieved_chunks": [
                Document(page_content="chunk", metadata={}),
            ],
        }

        with patch("docops.rag.verifier.config") as mock_cfg:
            mock_cfg.min_citations = 1
            mock_cfg.max_retries = 2

            result = verify_grounding(state)
            assert result["grounding_ok"] is False
            assert result["retry"] is False
            assert "inexistentes" in result["disclaimer"]

    def test_valid_citations_pass(self):
        from docops.rag.verifier import verify_grounding

        state = {
            "answer": "Segundo [Fonte 1] e [Fonte 2], o resultado é 42%",
            "retry_count": 0,
            "retrieved_chunks": [
                Document(page_content="chunk 1", metadata={}),
                Document(page_content="chunk 2", metadata={}),
            ],
        }

        with patch("docops.rag.verifier.config") as mock_cfg:
            mock_cfg.min_citations = 2
            mock_cfg.max_retries = 2

            result = verify_grounding(state)
            assert result["grounding_ok"] is True

    def test_empty_retrieval_produces_disclaimer(self):
        from docops.rag.verifier import verify_grounding

        state = {
            "answer": "Não sei",
            "retry_count": 3,
            "retrieved_chunks": [],
        }

        with patch("docops.rag.verifier.config") as mock_cfg:
            mock_cfg.max_retries = 2

            result = verify_grounding(state)
            assert result["grounding_ok"] is False
            assert "Não foram encontrados" in result["disclaimer"]
