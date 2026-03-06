"""Markdown-aware splitter that preserves section hierarchy as metadata.

Splits Markdown documents by ATX headings (# H1, ## H2, etc.), producing
chunks with ``section_title`` and ``section_path`` metadata (breadcrumbs).
Large sections are sub-divided while keeping section metadata intact.
"""

import re
from typing import List

from langchain_core.documents import Document

from docops.ingestion.metadata import (
    build_chunk_id,
    build_doc_id,
    infer_file_type,
    normalize_source_path,
    normalize_chunk_metadata,
)
from docops.logging import get_logger

logger = get_logger("docops.ingestion.md_splitter")

# ATX heading: optional leading whitespace, 1-6 hashes, space, title
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _heading_level(hashes: str) -> int:
    return len(hashes)


def _build_section_path(hierarchy: dict) -> str:
    """Build breadcrumb path from hierarchy dict {level: title}."""
    if not hierarchy:
        return ""
    parts = [hierarchy[lvl] for lvl in sorted(hierarchy.keys())]
    return " > ".join(p for p in parts if p)


def _split_text_with_overlap(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Character-based splitting with overlap, respecting paragraph boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to cut at a paragraph boundary
        if end < len(text):
            para_break = chunk.rfind("\n\n")
            sentence_break = chunk.rfind(". ")
            cut = max(para_break, sentence_break)
            if cut > int(chunk_size * 0.5):
                chunk = text[start : start + cut + 1]
                end = start + cut + 1

        chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap

    return chunks


def _fallback_split(doc: Document, chunk_size: int, chunk_overlap: int) -> List[Document]:
    """Size-based fallback when document has no headings."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    raw_chunks = splitter.split_documents([doc])
    for i, chunk in enumerate(raw_chunks):
        chunk.metadata["file_type"] = "md"
        chunk.metadata["section_title"] = ""
        chunk.metadata["section_path"] = ""
        normalize_chunk_metadata(chunk, chunk_index=i, stable_ids=True)

    return raw_chunks


def split_markdown(
    doc: Document,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> List[Document]:
    """Split a Markdown document by headings, preserving section hierarchy.

    Each output chunk gets:
    - ``section_title``: the immediate heading title (empty for preamble)
    - ``section_path``: breadcrumb path, e.g. "Arquitetura > Retrieval > Reranking"
    - ``file_type``: "md"
    - ``chunk_id``: deterministic SHA-256 hash
    - ``chunk_index``: sequential index within this document
    """
    text = doc.page_content
    file_name = str(doc.metadata.get("file_name") or "unknown")
    source_path = normalize_source_path(doc.metadata)
    doc_id = doc.metadata.get("doc_id") or build_doc_id(source_path)
    file_type = infer_file_type(doc.metadata) or "md"

    # Find all headings and their positions
    heading_matches = list(_HEADING_RE.finditer(text))
    if not heading_matches:
        return _fallback_split(doc, chunk_size, chunk_overlap)

    # Build sections: list of {start, end, level, title, content}
    sections = []

    # Preamble before first heading
    first_heading_start = heading_matches[0].start()
    if first_heading_start > 0:
        preamble = text[:first_heading_start].strip()
        if preamble:
            sections.append(
                {"level": 0, "title": "", "content": preamble}
            )

    for i, match in enumerate(heading_matches):
        section_end = (
            heading_matches[i + 1].start()
            if i + 1 < len(heading_matches)
            else len(text)
        )
        content = text[match.start() : section_end]
        sections.append(
            {
                "level": _heading_level(match.group(1)),
                "title": match.group(2).strip(),
                "content": content,
            }
        )

    # Walk sections, maintaining heading hierarchy
    hierarchy: dict = {}  # {level: title}
    chunks: List[Document] = []
    chunk_idx = 0

    for section in sections:
        level = section["level"]
        title = section["title"]
        content = section["content"]

        if level > 0:
            hierarchy[level] = title
            # Clear all deeper levels
            for deeper in [k for k in list(hierarchy.keys()) if k > level]:
                del hierarchy[deeper]

        section_path = _build_section_path(hierarchy)

        sub_texts = _split_text_with_overlap(content, chunk_size, chunk_overlap)

        for sub in sub_texts:
            stripped = sub.strip()
            if not stripped:
                continue

            chunk = Document(
                page_content=stripped,
                metadata={
                    **doc.metadata,
                    "doc_id": doc_id,
                    "source_path": source_path,
                    "file_type": file_type,
                    "section_title": title,
                    "section_path": section_path,
                    "chunk_index": chunk_idx,
                    "page": doc.metadata.get("page") or "N/A",
                    "page_start": doc.metadata.get("page_start", doc.metadata.get("page") or "N/A"),
                    "page_end": doc.metadata.get("page_end", doc.metadata.get("page") or "N/A"),
                },
            )
            chunk.metadata["chunk_id"] = build_chunk_id(stripped, chunk.metadata)
            chunks.append(chunk)
            chunk_idx += 1

    logger.info(
        f"Markdown split: '{file_name}' → {len(chunks)} chunks "
        f"({len(sections)} sections detected)"
    )
    return chunks
