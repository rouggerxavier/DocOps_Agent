"""Text splitter: chunks documents while preserving source metadata.

When STRUCTURED_CHUNKING=true (default), dispatches Markdown and plain-text
files to specialised splitters that detect section headings and emit
``section_title`` / ``section_path`` metadata.  PDF files keep the existing
size-based approach but also receive the normalised metadata fields.

Output metadata schema (all chunks):
    doc_id, source_path, file_type, page, page_start, page_end
    section_title, section_path
    chunk_id (stable SHA-256), chunk_index
"""

import uuid
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from docops.ingestion.metadata import build_chunk_id, normalize_chunk_metadata
from docops.logging import get_logger

logger = get_logger("docops.ingestion.splitter")


def _stable_chunk_id(file_name: str, chunk_index: int, text: str) -> str:
    """Backward-compatible helper used by tests.

    Maps ``chunk_index`` into ``section_path`` so IDs remain deterministic and
    distinct across chunks from the same file/content.
    """
    meta = {
        "source_path": file_name,
        "page_start": "N/A",
        "page_end": "N/A",
        "section_path": f"chunk:{chunk_index}",
    }
    return build_chunk_id(text, meta)


def _enrich_chunk_metadata(chunk: Document, idx: int, stable_ids: bool) -> None:
    """Ensure all expected metadata fields are present on a chunk (in-place)."""
    normalize_chunk_metadata(chunk, chunk_index=idx, stable_ids=stable_ids)
    if not stable_ids:
        chunk.metadata["chunk_id"] = str(uuid.uuid4())


def split_documents(
    docs: List[Document],
    chunk_size: int = 900,
    chunk_overlap: int = 150,
    stable_ids: bool = True,
    structured: bool | None = None,
) -> List[Document]:
    """Split documents into chunks, routing to specialised splitters when applicable.

    Routing (when ``structured=True``, the default from ``STRUCTURED_CHUNKING``):
    - ``.md`` / ``.markdown`` → :mod:`docops.ingestion.md_splitter`
    - ``.txt`` → :mod:`docops.ingestion.txt_splitter`
    - ``.pdf`` and everything else → RecursiveCharacterTextSplitter (size-based)

    All chunks receive the unified metadata schema including:
    ``doc_id``, ``source_path``, ``file_type``, ``page_start``, ``page_end``,
    ``section_title``, ``section_path`` and stable ``chunk_id``.

    Args:
        docs: List of Document objects to split.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between chunks.
        stable_ids: If True, use SHA-256 hash for deterministic IDs.
        structured: Override STRUCTURED_CHUNKING config. None = read config.
    """
    if not docs:
        return []

    if structured is None:
        from docops.config import config as _cfg
        structured = _cfg.structured_chunking

    md_docs: List[Document] = []
    txt_docs: List[Document] = []
    other_docs: List[Document] = []

    for doc in docs:
        fname = doc.metadata.get("file_name", doc.metadata.get("source", ""))
        ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        if structured and ext in ("md", "markdown"):
            md_docs.append(doc)
        elif structured and ext == "txt":
            txt_docs.append(doc)
        else:
            other_docs.append(doc)

    all_chunks: List[Document] = []

    # ── Markdown ──────────────────────────────────────────────────────────────
    if md_docs:
        from docops.ingestion.md_splitter import split_markdown
        for doc in md_docs:
            chunks = split_markdown(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            for i, chunk in enumerate(chunks):
                _enrich_chunk_metadata(
                    chunk, chunk.metadata.get("chunk_index", i), stable_ids
                )
            all_chunks.extend(chunks)

    # ── Plain text ────────────────────────────────────────────────────────────
    if txt_docs:
        from docops.ingestion.txt_splitter import split_txt
        for doc in txt_docs:
            chunks = split_txt(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            for i, chunk in enumerate(chunks):
                _enrich_chunk_metadata(
                    chunk, chunk.metadata.get("chunk_index", i), stable_ids
                )
            all_chunks.extend(chunks)

    # ── PDF and other ─────────────────────────────────────────────────────────
    if other_docs:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )
        raw_chunks = splitter.split_documents(other_docs)
        for i, chunk in enumerate(raw_chunks):
            fname = chunk.metadata.get("file_name", chunk.metadata.get("source", ""))
            ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
            chunk.metadata["file_type"] = ext or "unknown"
            _enrich_chunk_metadata(chunk, i, stable_ids)
        all_chunks.extend(raw_chunks)

    logger.info(
        f"split_documents: {len(docs)} docs → {len(all_chunks)} chunks "
        f"(size={chunk_size}, overlap={chunk_overlap}, structured={structured})"
    )
    return all_chunks
