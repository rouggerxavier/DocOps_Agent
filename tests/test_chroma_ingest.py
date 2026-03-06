"""Integration test: ingest chunks into Chroma with FakeEmbeddings (no API call)."""

import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.documents import Document


class FakeEmbeddings:
    """Deterministic fake embeddings that return a fixed-length float vector.
    Implements the minimal interface expected by langchain_chroma.Chroma.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 10) / 10.0] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 8


def _make_chunk(text: str, file_name: str = "test.txt") -> Document:
    return Document(
        page_content=text,
        metadata={
            "chunk_id": str(uuid.uuid4()),
            "file_name": file_name,
            "source": f"docs/{file_name}",
            "page": "N/A",
        },
    )


def test_index_chunks_persists_to_chroma():
    """index_chunks stores documents; list_indexed_docs returns them."""
    from docops.ingestion.indexer import index_chunks, list_indexed_docs

    fake_emb = FakeEmbeddings()
    chunks = [
        _make_chunk("Alpha content about machine learning.", file_name="alpha.txt"),
        _make_chunk("Beta content about neural networks.", file_name="alpha.txt"),
        _make_chunk("Gamma content about data pipelines.", file_name="gamma.txt"),
    ]

    tmpdir = tempfile.mkdtemp()
    try:
        with patch("docops.ingestion.indexer.config") as mock_config:
            mock_config.chroma_dir = Path(tmpdir) / "chroma"
            mock_config.gemini_api_key = "fake-key"

            count = index_chunks(chunks, embeddings=fake_emb)
            assert count == 3

            docs = list_indexed_docs(embeddings=fake_emb)

        file_names = {d["file_name"] for d in docs}
        assert "alpha.txt" in file_names
        assert "gamma.txt" in file_names

        alpha_entry = next(d for d in docs if d["file_name"] == "alpha.txt")
        assert alpha_entry["chunk_count"] == 2

        gamma_entry = next(d for d in docs if d["file_name"] == "gamma.txt")
        assert gamma_entry["chunk_count"] == 1
    finally:
        # On Windows, Chroma holds file locks; ignore cleanup errors
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_index_chunks_empty():
    """index_chunks with no chunks returns 0."""
    from docops.ingestion.indexer import index_chunks

    fake_emb = FakeEmbeddings()
    tmpdir = tempfile.mkdtemp()
    try:
        with patch("docops.ingestion.indexer.config") as mock_config:
            mock_config.chroma_dir = Path(tmpdir) / "chroma"
            mock_config.gemini_api_key = "fake-key"

            count = index_chunks([], embeddings=fake_emb)
        assert count == 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_retrieve_with_fake_embeddings():
    """retrieve() returns Documents after indexing with FakeEmbeddings."""
    from docops.ingestion.indexer import index_chunks
    from langchain_chroma import Chroma

    fake_emb = FakeEmbeddings()
    chunks = [
        _make_chunk("The quick brown fox jumps over the lazy dog.", file_name="fox.txt"),
        _make_chunk("Machine learning is a subset of artificial intelligence.", file_name="ml.txt"),
    ]

    tmpdir = tempfile.mkdtemp()
    try:
        chroma_path = Path(tmpdir) / "chroma"

        with patch("docops.ingestion.indexer.config") as mock_index_cfg:
            mock_index_cfg.chroma_dir = chroma_path
            mock_index_cfg.gemini_api_key = "fake-key"
            index_chunks(chunks, embeddings=fake_emb)

        # Open the same store and verify similarity_search works
        live_vs = Chroma(
            collection_name="docops",
            embedding_function=fake_emb,
            persist_directory=str(chroma_path),
        )
        results = live_vs.similarity_search("fox", k=2)
        del live_vs  # release file handles before cleanup

        assert isinstance(results, list)
        assert len(results) >= 1
        assert all(isinstance(r, Document) for r in results)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
