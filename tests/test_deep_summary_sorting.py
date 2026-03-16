from langchain_core.documents import Document

from docops.summarize.pipeline import _sort_chunks


def _doc(chunk_index, page_start=None, page=None, page_end=None):
    metadata = {
        "chunk_index": chunk_index,
        "page_start": page_start,
        "page": page,
        "page_end": page_end,
    }
    return Document(page_content="x", metadata=metadata)


def test_sort_chunks_handles_non_numeric_page_metadata_without_crashing():
    chunks = [
        _doc("1", page_start=None, page="N/A", page_end=None),
        _doc("0", page_start="2", page=None, page_end="2"),
    ]

    sorted_chunks = _sort_chunks(chunks)

    assert len(sorted_chunks) == 2
    assert sorted_chunks[0].metadata["chunk_index"] == "0"
    assert sorted_chunks[1].metadata["chunk_index"] == "1"


def test_sort_chunks_uses_safe_fallback_for_invalid_chunk_index():
    chunks = [
        _doc("invalid", page_start="1", page_end="1"),
        _doc("2", page_start="1", page_end="1"),
        _doc(None, page_start="1", page_end="1"),
    ]

    sorted_chunks = _sort_chunks(chunks)

    ordered_chunk_indexes = [d.metadata["chunk_index"] for d in sorted_chunks]
    assert ordered_chunk_indexes[0] == "2"
    assert "invalid" in ordered_chunk_indexes[1:]
    assert None in ordered_chunk_indexes[1:]
