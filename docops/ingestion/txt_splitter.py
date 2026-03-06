"""TXT-aware splitter that detects section headings via heuristics.

Recognises "titles" by:
1. Lines in ALL CAPS (at least 3 chars, at most 120)
2. Lines that end with ':'
3. Numbered headings: '1.', '1.1', '1.1.1' followed by text

Falls back to size-based splitting when no headings are detected.
"""

import re
from typing import List, Tuple

from langchain_core.documents import Document

from docops.ingestion.metadata import (
    build_chunk_id,
    build_doc_id,
    infer_file_type,
    normalize_chunk_metadata,
    normalize_source_path,
)
from docops.logging import get_logger

logger = get_logger("docops.ingestion.txt_splitter")

# Heading detection patterns
_HEADING_PATTERNS = [
    # ALL CAPS lines (supports PT accents)
    re.compile(r"^[A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜ\s]{3,120}$"),
    # Lines ending with colon  (min 3 chars before the colon)
    re.compile(r"^.{3,80}:\s*$"),
    # Numbered sections: 1. / 1.1 / 1.1.1 Title
    re.compile(r"^\d+(?:\.\d+)*(?:[\.\)]?)\s+\S"),
]


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 3 or len(stripped) > 120:
        return False
    return any(p.match(stripped) for p in _HEADING_PATTERNS)


def _split_into_sections(text: str) -> List[Tuple[str, str]]:
    """Return list of (section_title, section_content) tuples.

    The first element may have an empty title (text before the first heading).
    """
    lines = text.splitlines(keepends=True)
    sections: List[Tuple[str, str]] = []
    current_title = ""
    current_lines: List[str] = []

    for line in lines:
        if _is_heading_line(line):
            # Flush current section
            content = "".join(current_lines).strip()
            if content:
                sections.append((current_title, content))
            current_title = line.strip().rstrip(":")
            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush last section
    content = "".join(current_lines).strip()
    if content:
        sections.append((current_title, content))

    return sections if sections else [("", text.strip())]


def _split_text_with_overlap(text: str, chunk_size: int, overlap: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Cut at sentence boundary when possible
        if end < len(text):
            cut = max(chunk.rfind("\n\n"), chunk.rfind(". "))
            if cut > int(chunk_size * 0.5):
                chunk = text[start : start + cut + 1]
                end = start + cut + 1

        chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def split_txt(
    doc: Document,
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> List[Document]:
    """Split a plain-text document using heuristic heading detection.

    Each chunk gets:
    - ``section_title``: detected heading (empty if not detected)
    - ``section_path``: same as section_title (TXT is flat)
    - ``file_type``: "txt"
    - ``chunk_id``: deterministic SHA-256 hash
    - ``chunk_index``: sequential index
    """
    file_name = doc.metadata.get("file_name", "unknown")
    source_path = normalize_source_path(doc.metadata)
    doc_id = doc.metadata.get("doc_id") or build_doc_id(source_path)
    file_type = infer_file_type(doc.metadata) or "txt"
    sections = _split_into_sections(doc.page_content)

    chunks: List[Document] = []
    chunk_idx = 0

    for title, content in sections:
        if not content.strip():
            continue

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
                    "section_path": title,
                    "chunk_index": chunk_idx,
                    "page": doc.metadata.get("page") or "N/A",
                    "page_start": doc.metadata.get(
                        "page_start", doc.metadata.get("page") or "N/A"
                    ),
                    "page_end": doc.metadata.get(
                        "page_end", doc.metadata.get("page") or "N/A"
                    ),
                },
            )
            normalize_chunk_metadata(chunk, chunk_index=chunk_idx, stable_ids=True)
            chunk.metadata["chunk_id"] = build_chunk_id(stripped, chunk.metadata)
            chunks.append(chunk)
            chunk_idx += 1

    logger.info(
        f"TXT split: '{file_name}' → {len(chunks)} chunks "
        f"({len(sections)} sections detected)"
    )
    return chunks
