"""Tests for the text splitter."""

import pytest
from langchain_core.documents import Document

from docops.ingestion.splitter import split_documents


def _make_doc(text: str, file_name: str = "test.txt", page: int = 1) -> Document:
    return Document(
        page_content=text,
        metadata={"file_name": file_name, "source": f"docs/{file_name}", "page": page},
    )


def test_split_short_doc_produces_one_chunk():
    """A short document should produce exactly one chunk."""
    doc = _make_doc("Short content that fits in one chunk.")
    chunks = split_documents([doc], chunk_size=900, chunk_overlap=150)
    assert len(chunks) == 1


def test_split_long_doc_produces_multiple_chunks():
    """A document larger than chunk_size should be split."""
    long_text = "Este é um parágrafo de teste. " * 100  # ~3000 chars
    doc = _make_doc(long_text)
    chunks = split_documents([doc], chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1


def test_each_chunk_has_chunk_id():
    """Every chunk must have a unique chunk_id."""
    doc = _make_doc("Alpha. " * 50)
    chunks = split_documents([doc], chunk_size=100, chunk_overlap=10)
    ids = [c.metadata["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "chunk_ids must be unique"


def test_metadata_preserved():
    """Source metadata must carry through to all chunks."""
    doc = _make_doc("Content. " * 60, file_name="manual.pdf", page=3)
    chunks = split_documents([doc], chunk_size=200, chunk_overlap=20)
    for chunk in chunks:
        assert chunk.metadata["file_name"] == "manual.pdf"
        assert chunk.metadata["source"] == "docs/manual.pdf"
        assert chunk.metadata["page"] == 3


def test_empty_input_returns_empty_list():
    """Empty input should return empty list without errors."""
    result = split_documents([])
    assert result == []


def test_none_page_normalized():
    """Page=None should be normalized to 'N/A'."""
    doc = Document(
        page_content="Some content here. " * 20,
        metadata={"file_name": "note.md", "source": "docs/note.md", "page": None},
    )
    chunks = split_documents([doc])
    for chunk in chunks:
        assert chunk.metadata["page"] == "N/A"


def test_overlap_creates_shared_content():
    """With overlap, adjacent chunks should share some content."""
    # Create text with clearly defined sentences
    text = " ".join([f"Sentence {i} is here and has some words in it." for i in range(30)])
    doc = _make_doc(text)
    chunks = split_documents([doc], chunk_size=200, chunk_overlap=50)

    if len(chunks) >= 2:
        # The end of chunk 0 and start of chunk 1 should have some overlap
        end_of_first = chunks[0].page_content[-50:]
        start_of_second = chunks[1].page_content[:100]
        # There should be some shared words
        end_words = set(end_of_first.split())
        start_words = set(start_of_second.split())
        # With overlap=50 there should be at least some shared content
        assert len(end_words & start_words) > 0 or len(chunks) == 1
