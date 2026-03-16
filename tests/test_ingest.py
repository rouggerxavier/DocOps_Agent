"""Tests for the ingestion pipeline (loaders + splitter + indexer)."""

import os
import tempfile
from pathlib import Path

import pytest
from langchain_core.documents import Document

from docops.ingestion.loaders import (
    load_text,
    load_markdown,
    load_csv,
    load_xlsx,
    load_directory,
    SUPPORTED_EXTENSIONS,
)
from docops.ingestion.splitter import split_documents


# ── Loader tests ─────────────────────────────────────────────────────────────

def test_load_text_returns_document():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello DocOps!\nThis is a test document.")
        tmp = Path(f.name)
    try:
        docs = load_text(tmp)
        assert len(docs) == 1
        assert "Hello DocOps!" in docs[0].page_content
        assert docs[0].metadata["file_name"] == tmp.name
    finally:
        tmp.unlink()


def test_load_markdown_returns_document():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Title\n\nThis is **markdown** content.")
        tmp = Path(f.name)
    try:
        docs = load_markdown(tmp)
        assert len(docs) == 1
        assert "markdown" in docs[0].page_content
        assert docs[0].metadata["page"] == "N/A"
    finally:
        tmp.unlink()


def test_load_csv_returns_document():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("nome,idade\nAna,21\nBruno,34\n")
        tmp = Path(f.name)
    try:
        docs = load_csv(tmp)
        assert len(docs) == 1
        assert "Tabela CSV" in docs[0].page_content
        assert "nome: Ana" in docs[0].page_content
        assert docs[0].metadata["file_type"] == "csv"
    finally:
        tmp.unlink()


def test_load_xlsx_returns_sheet_documents():
    openpyxl = pytest.importorskip("openpyxl")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp = Path(f.name)

    try:
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Dados"
        ws1.append(["nome", "nota"])
        ws1.append(["Ana", 9.5])
        ws2 = wb.create_sheet("Resumo")
        ws2.append(["topico", "status"])
        ws2.append(["ID3", "ok"])
        wb.save(tmp)
        wb.close()

        docs = load_xlsx(tmp)
        assert len(docs) == 2
        assert all(d.metadata["file_type"] == "xlsx" for d in docs)
        assert any(d.metadata["section_title"] == "Dados" for d in docs)
        assert any("Planilha XLSX" in d.page_content for d in docs)
    finally:
        tmp.unlink(missing_ok=True)


def test_load_text_metadata():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Content here.")
        tmp = Path(f.name)
    try:
        docs = load_text(tmp)
        meta = docs[0].metadata
        assert "file_name" in meta
        assert "source" in meta
        assert "source_path" in meta
        assert "doc_id" in meta
        assert "file_type" in meta
        assert "page_start" in meta
        assert "page_end" in meta
        assert meta["source"] == str(tmp)
    finally:
        tmp.unlink()


def test_load_directory_finds_txt_and_md():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        (d / "a.txt").write_text("File A content.")
        (d / "b.md").write_text("# File B")
        (d / "ignore.json").write_text("{}")  # Should be ignored

        docs = load_directory(d)
        names = [doc.metadata["file_name"] for doc in docs]
        assert "a.txt" in names
        assert "b.md" in names
        # JSON file should not be loaded
        assert all(".json" not in n for n in names)


def test_load_directory_empty_returns_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        docs = load_directory(Path(tmpdir))
        assert docs == []


def test_load_directory_nonexistent_raises():
    with pytest.raises(FileNotFoundError):
        load_directory(Path("/nonexistent/path/xyz"))


def test_supported_extensions():
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".txt" in SUPPORTED_EXTENSIONS
    assert ".md" in SUPPORTED_EXTENSIONS
    assert ".csv" in SUPPORTED_EXTENSIONS
    assert ".xlsx" in SUPPORTED_EXTENSIONS


# ── Ingestion pipeline integration ───────────────────────────────────────────

def test_full_ingestion_pipeline_txt():
    """Full pipeline: load → split → verify chunks have all required metadata."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        # Write enough content to produce multiple chunks
        f.write("DocOps test content.\n" * 100)
        tmp = Path(f.name)
    try:
        docs = load_text(tmp)
        chunks = split_documents(docs, chunk_size=200, chunk_overlap=20)

        assert len(chunks) > 0
        for chunk in chunks:
            assert "chunk_id" in chunk.metadata
            assert "file_name" in chunk.metadata
            assert "source" in chunk.metadata
            assert len(chunk.page_content) > 0
    finally:
        tmp.unlink()


def test_ingestion_preserves_file_name():
    """File name in metadata must match the actual file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="my_doc_"
    ) as f:
        f.write("Test content for file name preservation. " * 10)
        tmp = Path(f.name)
    try:
        docs = load_text(tmp)
        chunks = split_documents(docs)
        for chunk in chunks:
            assert chunk.metadata["file_name"] == tmp.name
    finally:
        tmp.unlink()
