"""Tests for metadata persistence and embedding text enrichment."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float((i % 7) + 1) / 10.0] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 8


def _chunk() -> Document:
    return Document(
        page_content="Texto principal da seção sobre retrieval e reranking.",
        metadata={
            "file_name": "manual.md",
            "source": "docs/manual.md",
            "source_path": "docs/manual.md",
            "doc_id": "doc_manual",
            "file_type": "md",
            "page": "N/A",
            "page_start": "N/A",
            "page_end": "N/A",
            "section_title": "Retrieval",
            "section_path": "Arquitetura > Retrieval > Reranking",
            "chunk_id": "chunk_manual_1",
            "chunk_index": 0,
        },
    )


def test_index_persists_structured_metadata():
    from docops.ingestion.indexer import get_vectorstore, index_chunks

    emb = FakeEmbeddings()
    tmpdir = tempfile.mkdtemp()
    try:
        chroma_dir = Path(tmpdir) / "chroma"
        with patch("docops.ingestion.indexer.config") as mock_cfg:
            mock_cfg.chroma_dir = chroma_dir
            mock_cfg.gemini_api_key = "fake-key"
            mock_cfg.ingest_incremental = False

            count = index_chunks([_chunk()], embeddings=emb, incremental=False)
            assert count == 1

            vs = get_vectorstore(embeddings=emb)
            raw = vs._collection.get(include=["metadatas", "documents"])
            del vs

        assert raw["metadatas"], "Expected at least one metadata entry"
        meta = raw["metadatas"][0]
        assert meta["doc_id"]
        assert meta["source_path"] == "docs/manual.md"
        assert meta["file_type"] == "md"
        assert "section_path" in meta
        assert "page_start" in meta
        assert "page_end" in meta
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_embedding_text_includes_section_prefix():
    from docops.ingestion.indexer import get_vectorstore, index_chunks

    emb = FakeEmbeddings()
    tmpdir = tempfile.mkdtemp()
    try:
        chroma_dir = Path(tmpdir) / "chroma"
        with patch("docops.ingestion.indexer.config") as mock_cfg:
            mock_cfg.chroma_dir = chroma_dir
            mock_cfg.gemini_api_key = "fake-key"
            mock_cfg.ingest_incremental = False

            index_chunks([_chunk()], embeddings=emb, incremental=False)
            vs = get_vectorstore(embeddings=emb)
            raw = vs._collection.get(include=["documents"])
            del vs

        stored_text = raw["documents"][0]
        assert stored_text.startswith("[meta] ")
        assert "section_path:" in stored_text
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
