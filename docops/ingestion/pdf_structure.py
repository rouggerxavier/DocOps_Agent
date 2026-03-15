"""PDF structure inference: infer section headings and structure from PDF page text.

When PDFs are loaded page-by-page, chunks typically lack section_title/section_path
metadata. This module infers structure from textual heuristics so that the deep-summary
pipeline can use section-based grouping instead of falling back to blind windows.

Heuristics used (language-agnostic, works for PT-BR and EN):
  1. Short title-like first lines (≤ 120 chars, title-case or ALL-CAPS).
  2. TOC-like pages (many short numbered lines).
  3. Numbered headings (1., 1.1, 2.3.1, etc.).
  4. Repeated heading patterns across pages.
  5. Lexical transition detection (topic shift between consecutive pages).

The module enriches chunk metadata in-place without altering page_content.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document

from docops.logging import get_logger

logger = get_logger("docops.ingestion.pdf_structure")

# ── Heuristic patterns ────────────────────────────────────────────────────────

# Title-like line: prefer explicit heading formats, ALL-CAPS, or compact title-case.
_UPPER_TITLE_RE = re.compile(
    r"^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑ0-9\s\-:,/()]{2,118}$"
)
_WORD_RE = re.compile(r"[A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇÑáàâãéêíóôõúçñ]+")

_LOWER_CONNECTORS = {
    "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "sem",
    "a", "o", "as", "os", "no", "na", "nos", "nas", "to", "of", "and", "or",
    "for", "in", "on", "with", "by", "the", "an", "at",
}

_SENTENCE_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|being|been|uses?|shows?|discuss(?:es|ed)?|"
    r"presents?|contains?|explains?|applies?|can|should|will|tem|usa|mostra|"
    r"discute|apresenta|cont[eé]m|explica|pode|deve|ser[aá])\b",
    re.IGNORECASE,
)

# Numbered heading: "1.", "1.1", "2.3.1", etc. followed by text.
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d{1,3}(?:\.\d{1,3}){0,3})\.?\s+([A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑa-záàâãéêíóôõúçñ].{2,100})$"
)

# TOC line: "1.1 Topic Name .... 5" or "Chapter 2 - Topic"
_TOC_LINE_RE = re.compile(
    r"^\s*(?:\d{1,3}(?:\.\d{1,3}){0,3}\.?\s+.{3,80}\s*\.{2,}\s*\d+\s*"
    r"|\d{1,3}(?:\.\d{1,3}){0,3}\.?\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑa-záàâãéêíóôõúçñ].{2,80})\s*$"
)

# Chapter/Section markers (PT-BR + EN).
_CHAPTER_MARKER_RE = re.compile(
    r"^\s*(?:cap[ií]tulo|chapter|se[çc][aã]o|section|parte|part|módulo|module"
    r"|unidade|unit|aula|le[çc][aã]o|lesson|tema|topic)\s+\d",
    re.IGNORECASE,
)

# Slide number patterns (common in slide decks).
_SLIDE_NUMBER_RE = re.compile(r"^\s*(?:slide|página|page|p\.?|lâmina)?\s*\d{1,4}\s*$", re.IGNORECASE)

# Embedding metadata header artifacts.
_META_HEADER_LINE_RE = re.compile(r"^\s*\[meta\]\s*", re.IGNORECASE)
_META_SECTION_VALUE_RE = re.compile(
    r"^\s*\[meta\]\s*(?:section_path|section_title|page(?:_range)?)\s*:",
    re.IGNORECASE,
)

# Short line threshold for title detection.
_MAX_TITLE_LINE_LEN = 120
_MIN_TITLE_LINE_LEN = 3
_MAX_TITLE_WORDS = 12


def _strip_embedding_header(text: str) -> str:
    """Drop leading [meta] embedding header lines from chunk content."""
    if not text:
        return ""
    lines = text.splitlines()
    idx = 0
    while idx < len(lines) and _META_HEADER_LINE_RE.match(lines[idx].strip()):
        idx += 1
    if idx == 0:
        return text
    return "\n".join(lines[idx:])


def _is_valid_section_label(text: str) -> bool:
    """Reject noisy / non-semantic strings that should never be section titles.

    A valid section label must have:
    - Sufficient alphabetic density (letters ÷ non-space chars ≥ 0.50).
    - At least one real word (≥ 2 consecutive alpha characters).
    - Not be a pure numeric/symbol token (e.g. "+1 t3", "-- //", "***").

    This filter is applied to ALL inferred titles, including lexical-transition
    fallback titles, to prevent noisy PDF extraction artifacts from becoming
    section headings.
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    # Non-space characters: letters, digits, punctuation, symbols.
    non_space = re.sub(r"\s", "", stripped)
    if not non_space:
        return False
    alpha_count = sum(1 for c in non_space if c.isalpha())
    alpha_ratio = alpha_count / len(non_space)
    if alpha_ratio < 0.50:
        return False
    # Must contain at least one real word (2+ consecutive alpha chars).
    if not re.search(r"[A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇÑáàâãéêíóôõúçñ]{2,}", stripped):
        return False
    return True


def _clean_section_label(value: str | None) -> str:
    """Normalize section labels and reject [meta] artifacts."""
    label = str(value or "").strip()
    if not label:
        return ""
    if _META_SECTION_VALUE_RE.match(label) or _META_HEADER_LINE_RE.match(label):
        return ""
    label = re.sub(r"\s+", " ", label)
    if not _is_valid_section_label(label):
        return ""
    return label


def _get_first_salient_line(text: str) -> str | None:
    """Extract the first non-trivial line from page text."""
    text = _strip_embedding_header(text)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _META_HEADER_LINE_RE.match(stripped):
            continue
        # Skip slide numbers and very short noise.
        if _SLIDE_NUMBER_RE.match(stripped):
            continue
        if len(stripped) < _MIN_TITLE_LINE_LEN:
            continue
        return stripped
    return None


def _is_title_like(line: str) -> bool:
    """Heuristic: does this line look like a heading/title?"""
    if not line:
        return False
    line = line.strip()
    if len(line) > _MAX_TITLE_LINE_LEN:
        return False
    # Reject noisy/low-density strings early.
    if not _is_valid_section_label(line):
        return False
    # Numbered heading.
    if _NUMBERED_HEADING_RE.match(line):
        return True
    # Chapter/section marker.
    if _CHAPTER_MARKER_RE.match(line):
        return True
    if line.endswith((".", "?", "!")):
        return False

    # ALL-CAPS headings are common in slides.
    if _UPPER_TITLE_RE.match(line):
        return True

    words = _WORD_RE.findall(line)
    if not words or len(words) > _MAX_TITLE_WORDS:
        return False

    # Reject natural-language sentence-like lines.
    lower_words = [w.lower() for w in words]
    sentence_like = (
        len(words) >= 6 and _SENTENCE_VERB_RE.search(line)
    ) or (sum(1 for w in lower_words if w in _LOWER_CONNECTORS) >= 3 and len(words) >= 7)
    if sentence_like:
        return False

    # Title-case score over content words (ignoring short connectors).
    content_words = [w for w in words if w.lower() not in _LOWER_CONNECTORS]
    if not content_words:
        return False
    title_hits = sum(1 for w in content_words if w[0].isupper())
    title_ratio = title_hits / len(content_words)

    # Accept compact title-case lines.
    if title_ratio >= 0.7:
        return True

    return False


def _is_toc_page(text: str, min_toc_lines: int = 4) -> bool:
    """Detect TOC-like pages with many short structured lines."""
    text = _strip_embedding_header(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < min_toc_lines:
        return False
    toc_count = sum(1 for l in lines if _TOC_LINE_RE.match(l))
    return toc_count >= min_toc_lines and toc_count / len(lines) >= 0.4


def _extract_toc_topics(text: str) -> list[dict[str, str]]:
    """Extract topic entries from a TOC page."""
    text = _strip_embedding_header(text)
    topics: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _META_HEADER_LINE_RE.match(stripped):
            continue
        m = _NUMBERED_HEADING_RE.match(stripped)
        if m:
            topics.append({
                "number": m.group(1),
                "title": m.group(2).strip().rstrip(".…·"),
            })
            continue
        # Unnumbered TOC entry (short title-like line).
        clean = re.sub(r"\.{2,}\s*\d+\s*$", "", stripped).strip()
        if clean and 3 < len(clean) < 100 and _is_title_like(clean):
            topics.append({"number": "", "title": clean})
    return topics


def _compute_lexical_distance(text_a: str, text_b: str) -> float:
    """Simple word-overlap distance between two texts. Returns 1.0 for completely different."""
    text_a = _strip_embedding_header(text_a)
    text_b = _strip_embedding_header(text_b)
    if not text_a or not text_b:
        return 1.0
    words_a = set(re.findall(r"\w{3,}", text_a.lower()))
    words_b = set(re.findall(r"\w{3,}", text_b.lower()))
    if not words_a or not words_b:
        return 1.0
    intersection = words_a & words_b
    union = words_a | words_b
    jaccard = len(intersection) / len(union) if union else 0.0
    return 1.0 - jaccard


def infer_pdf_structure(
    chunks: list[Document],
    transition_threshold: float = 0.75,
) -> list[Document]:
    """Enrich PDF chunks with inferred section_title and section_path metadata.

    This operates in-place on chunk metadata. Chunks that already have
    section_title/section_path are left unchanged.

    Args:
        chunks: Ordered list of Document chunks (sorted by page/chunk_index).
        transition_threshold: Lexical distance threshold for detecting topic
            transitions between consecutive chunks (0.0 = identical, 1.0 = different).

    Returns:
        The same list of chunks (modified in-place) for chaining convenience.
    """
    if not chunks:
        return chunks

    # Phase 1: Detect TOC pages and extract global topic list.
    toc_topics: list[dict[str, str]] = []
    for chunk in chunks:
        text = _strip_embedding_header(chunk.page_content or "").strip()
        if _is_toc_page(text):
            toc_topics.extend(_extract_toc_topics(text))

    # Phase 2: Build a heading lookup from TOC if available.
    toc_titles = [t["title"] for t in toc_topics if t.get("title")]

    # Phase 3: Per-chunk heading inference.
    current_section: str = ""
    section_path_parts: list[str] = []
    heading_changes = 0

    for i, chunk in enumerate(chunks):
        meta = chunk.metadata
        existing_title = _clean_section_label(meta.get("section_title"))
        existing_path = _clean_section_label(meta.get("section_path"))
        if existing_title != str(meta.get("section_title") or "").strip():
            meta["section_title"] = existing_title
        if existing_path != str(meta.get("section_path") or "").strip():
            meta["section_path"] = existing_path

        # Skip chunks that already have clean section metadata.
        if existing_title or existing_path:
            current_section = existing_title or existing_path
            if existing_path:
                section_path_parts = [p.strip() for p in existing_path.split(">") if p.strip()]
            else:
                section_path_parts = [current_section]
            continue

        # Only process PDF chunks.
        if str(meta.get("file_type", "")).lower() != "pdf":
            continue

        text = _strip_embedding_header(chunk.page_content or "").strip()
        if not text:
            continue

        inferred_title = ""

        # Strategy 1: First salient line as title.
        first_line = _get_first_salient_line(text)
        if first_line and _is_title_like(first_line):
            inferred_title = first_line.strip()

        # Strategy 2: Match against TOC topics.
        if not inferred_title and toc_titles:
            first_line = first_line or ""
            text_start = text[:300].lower()
            for toc_title in toc_titles:
                if toc_title.lower() in text_start:
                    inferred_title = toc_title
                    break

        # Strategy 3: Numbered heading anywhere in first few lines.
        if not inferred_title:
            for line in text.splitlines()[:5]:
                stripped = line.strip()
                m = _NUMBERED_HEADING_RE.match(stripped)
                if m:
                    inferred_title = stripped
                    break

        # Strategy 4: Chapter/section marker.
        if not inferred_title:
            for line in text.splitlines()[:3]:
                if _CHAPTER_MARKER_RE.match(line.strip()):
                    inferred_title = line.strip()
                    break

        # Strategy 5: Lexical transition detection.
        if not inferred_title and i > 0:
            prev_text = _strip_embedding_header(chunks[i - 1].page_content or "").strip()
            dist = _compute_lexical_distance(prev_text, text)
            if dist >= transition_threshold:
                # Major topic shift — use first salient line as best-effort title.
                if first_line and len(first_line) <= _MAX_TITLE_LINE_LEN:
                    inferred_title = first_line

        inferred_title = _clean_section_label(inferred_title)

        # Apply inferred structure.
        if inferred_title and inferred_title != current_section:
            current_section = inferred_title
            heading_changes += 1
            # Build hierarchical path from numbered headings.
            m = _NUMBERED_HEADING_RE.match(inferred_title)
            if m:
                num = m.group(1)
                depth = num.count(".") + 1
                title_text = _clean_section_label(m.group(2).strip()) or m.group(2).strip()
                # Keep path stack at correct depth.
                section_path_parts = section_path_parts[:depth - 1] + [title_text]
            else:
                section_path_parts = [inferred_title]

        if current_section:
            section_title = _clean_section_label(current_section)
            section_path = _clean_section_label(" > ".join(section_path_parts))
            if section_title:
                meta["section_title"] = section_title
                meta["section_path"] = section_path or section_title

    coverage = sum(
        1 for c in chunks
        if c.metadata.get("section_title") or c.metadata.get("section_path")
    )
    total = len(chunks)
    logger.info(
        "PDF structure inference: %d/%d chunks enriched (%d heading changes, %d TOC topics).",
        coverage, total, heading_changes, len(toc_topics),
    )
    return chunks


def extract_pdf_outline(chunks: list[Document]) -> list[dict[str, Any]]:
    """Extract a document outline from enriched PDF chunks.

    Returns a list of outline entries, each with:
        title: section heading text
        page_start: first page in this section
        page_end: last page in this section
        chunk_indices: list of chunk indices belonging to this section
    """
    if not chunks:
        return []

    outline: list[dict[str, Any]] = []
    current_title: str | None = None
    current_entry: dict[str, Any] | None = None

    for i, chunk in enumerate(chunks):
        meta = chunk.metadata
        title = _clean_section_label(meta.get("section_title", "") or meta.get("section_path", "") or "")

        if title != current_title:
            if current_entry:
                outline.append(current_entry)
            current_title = title
            page = _safe_int(meta.get("page_start", meta.get("page", 0)))
            current_entry = {
                "title": title or f"(Section {len(outline) + 1})",
                "page_start": page,
                "page_end": page,
                "chunk_indices": [i],
            }
        else:
            if current_entry:
                page = _safe_int(meta.get("page_end", meta.get("page", 0)))
                current_entry["page_end"] = max(current_entry["page_end"], page)
                current_entry["chunk_indices"].append(i)

    if current_entry:
        outline.append(current_entry)

    return outline


def _safe_int(val: Any) -> int:
    """Convert to int safely, returning 0 on failure."""
    try:
        return int(val) if val is not None and str(val).strip() not in ("", "N/A") else 0
    except (ValueError, TypeError):
        return 0
