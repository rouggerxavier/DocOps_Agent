"""Citation builder: formats source references from retrieved Document chunks."""

import os
import re
from typing import List

from langchain_core.documents import Document

# Max chars for the full chunk text injected into the LLM context.
# Configurable via CONTEXT_MAX_CHARS env var. 0 = no limit (use full text).
_DEFAULT_CONTEXT_MAX_CHARS = 1500


def _snippet(text: str, max_chars: int = 120) -> str:
    """Return a short snippet from the beginning of a text block.

    Used exclusively for the "Fontes:" section at the end of the answer.
    """
    text = text.strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    # Try to cut at a word boundary
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.7:
        truncated = truncated[:last_space]
    return truncated + "…"


def _strip_embedding_header(text: str) -> str:
    """Remove optional [meta] header used for embedding enrichment."""
    if text.startswith("[meta] "):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:]).lstrip()
    return text


def _context_text(text: str, max_chars: int | None = None) -> str:
    """Return the chunk text for the LLM context block.

    Unlike _snippet, this preserves as much of the original text as possible
    so the LLM has real content to reason about (not just a 120-char preview).
    """
    limit = max_chars if max_chars is not None else int(
        os.getenv("CONTEXT_MAX_CHARS", str(_DEFAULT_CONTEXT_MAX_CHARS))
    )

    text = _strip_embedding_header(text).strip()
    if limit <= 0 or len(text) <= limit:
        return text

    # Truncate at a word boundary
    truncated = text[:limit]
    last_space = truncated.rfind(" ")
    if last_space > limit * 0.7:
        truncated = truncated[:last_space]
    return truncated + "…"


def _format_location(meta: dict) -> str:
    """Build a human-readable location string from chunk metadata.

    Includes section breadcrumbs when available, e.g.:
        manual.md — Arquitetura > Retrieval, p. 3
    """
    fname = meta.get("file_name", "desconhecido")
    page = meta.get("page", "N/A")
    section_path = meta.get("section_path", "")
    section_title = meta.get("section_title", "")

    # Prefer section_path (breadcrumbs), fall back to section_title
    breadcrumb = section_path or section_title

    parts = [fname]
    if breadcrumb:
        parts.append(breadcrumb)
    if page and page != "N/A":
        parts.append(f"p. {page}")

    return " > ".join(parts)


def build_context_block(chunks: List[Document]) -> str:
    """Build the numbered context block injected into the synthesis prompt.

    Each chunk now includes section breadcrumbs (when available) plus the
    full chunk text (up to CONTEXT_MAX_CHARS characters).

    Format:
        [Fonte N] arquivo.md — Seção > Sub-seção (página X)
        <full chunk text>
        ---
    """
    if not chunks:
        return "(Nenhum trecho encontrado nos documentos.)"

    parts: List[str] = []
    for i, doc in enumerate(chunks, start=1):
        meta = doc.metadata
        fname = meta.get("file_name", "desconhecido")
        page = meta.get("page", "N/A")
        section_path = meta.get("section_path", "") or meta.get("section_title", "")
        page_str = f"página {page}" if page != "N/A" else "sem página"

        if section_path:
            header = f"[Fonte {i}] {fname} — {section_path} ({page_str})"
        else:
            header = f"[Fonte {i}] {fname} ({page_str})"

        content = _context_text(doc.page_content)
        parts.append(f"{header}\n{content}\n---")

    return "\n\n".join(parts)


def extract_evidence_snippet(text: str, query: str, window: int = 150) -> str:
    """Extract the most relevant snippet from *text* based on *query* keywords.

    Finds the region with the highest overlap of query tokens and returns
    a window of text around it. Falls back to the beginning of the text.
    """
    text = _strip_embedding_header(text)
    q_tokens = set(re.findall(r"\w+", query.lower()))
    if not q_tokens:
        return _snippet(text, max_chars=window)

    words = text.split()
    if not words:
        return ""

    best_pos = 0
    best_score = 0
    win_size = 20
    for i in range(len(words)):
        window_words = words[i:i + win_size]
        window_tokens = set(w.lower() for w in window_words)
        score = len(q_tokens & window_tokens)
        if score > best_score:
            best_score = score
            best_pos = i

    start = max(0, best_pos - 2)
    end = min(len(words), best_pos + win_size + 2)
    snippet = " ".join(words[start:end])

    if len(snippet) > window:
        snippet = snippet[:window]
        last_space = snippet.rfind(" ")
        if last_space > window * 0.7:
            snippet = snippet[:last_space]
        snippet += "…"

    return snippet


def build_sources_section(chunks: List[Document], query: str = "") -> str:
    """Build the 'Fontes:' section appended to every response.

    When section metadata is available, displays a breadcrumb path:
        [Fonte 1] **manual.md — Arquitetura > Retrieval, p. 3** — _snippet_

    Otherwise falls back to the previous compact format.
    """
    if not chunks:
        return "**Fontes:** (nenhuma fonte recuperada)"

    lines: List[str] = ["**Fontes:**"]
    for i, doc in enumerate(chunks, start=1):
        meta = doc.metadata
        chunk_id = meta.get("chunk_id", "")
        cid_short = chunk_id[:8] if chunk_id else ""

        location = _format_location(meta)
        if cid_short:
            location += f" [{cid_short}]"

        if query:
            snippet = extract_evidence_snippet(doc.page_content, query, window=100)
        else:
            snippet = _snippet(_strip_embedding_header(doc.page_content), max_chars=80)

        lines.append(f"- [Fonte {i}] **{location}** — _{snippet}_")

    return "\n".join(lines)


def build_summary_sources_section(
    chunks: List[Document],
    max_sources: int = 12,
) -> str:
    """Build a deduplicated 'Fontes:' section tailored for summary-mode responses.

    Unlike ``build_sources_section`` (one entry per chunk, which can produce
    hundreds of lines for large documents), this function groups chunks by their
    ``(file_name, section_path)`` pair, shows a page range, and caps the output
    at ``max_sources`` entries — keeping the section legible even for documents
    with 200+ chunks.

    Ordering: groups appear in document order (first chunk seen per group).

    Args:
        chunks: All document chunks used in the summary (ordered or not).
        max_sources: Hard cap on the number of source lines (default: 12).

    Returns:
        Formatted markdown string starting with ``**Fontes:**``.
    """
    if not chunks:
        return "**Fontes:** (nenhuma fonte recuperada)"

    # Collect group metadata in insertion order (preserves document order when
    # chunks are pre-sorted by chunk_index).
    seen: dict[tuple[str, str], dict] = {}
    for doc in chunks:
        meta = doc.metadata
        fname = meta.get("file_name", "desconhecido")
        section = (
            meta.get("section_path", "")
            or meta.get("section_title", "")
        )
        key = (fname, section)

        if key not in seen:
            seen[key] = {"pages": set()}

        page_val = meta.get("page") or meta.get("page_start")
        if page_val is not None:
            try:
                seen[key]["pages"].add(int(page_val))
            except (ValueError, TypeError):
                pass

    lines: List[str] = ["**Fontes:**"]
    total_groups = len(seen)

    for i, ((fname, section), info) in enumerate(seen.items(), start=1):
        if i > max_sources:
            break

        pages = sorted(info["pages"])
        if len(pages) == 1:
            page_str = f"p. {pages[0]}"
        elif len(pages) >= 2:
            page_str = f"pp. {pages[0]}–{pages[-1]}"
        else:
            page_str = ""

        parts: List[str] = [fname]
        if section:
            parts.append(section)
        if page_str:
            parts.append(page_str)

        location = " > ".join(parts)
        lines.append(f"- [Fonte {i}] **{location}**")

    if total_groups > max_sources:
        remainder = total_groups - max_sources
        lines.append(f"- _... e mais {remainder} seção(ões) do documento_")

    return "\n".join(lines)


def _format_anchor_source_line(source_idx: int, doc: Document) -> str:
    """Format one deep-summary source line preserving the source index label."""
    meta = doc.metadata
    fname = meta.get("file_name", "desconhecido")
    section = meta.get("section_path", "") or meta.get("section_title", "")

    page_start = meta.get("page_start") or meta.get("page")
    page_end = meta.get("page_end") or page_start

    page_str = ""
    if page_start is not None:
        try:
            ps = int(page_start)
            pe = int(page_end) if page_end is not None else ps
            page_str = f"pp. {ps}–{pe}" if ps != pe else f"p. {ps}"
        except (ValueError, TypeError):
            pass

    parts: List[str] = [fname]
    if section:
        parts.append(section)
    if page_str:
        parts.append(page_str)

    return f"- [Fonte {source_idx}] **{' > '.join(parts)}**"


def build_anchor_sources_section(
    anchors: List[Document],
    source_indices: List[int] | None = None,
) -> str:
    """Build 'Fontes:' for deep summary with stable source numbering.

    When ``source_indices`` is omitted, renders all anchors as [Fonte 1..N].
    When provided, renders only requested indices and preserves original labels.
    """
    if not anchors:
        return "**Fontes:** (nenhuma fonte recuperada)"

    lines: List[str] = ["**Fontes:**"]

    if source_indices is None:
        for i, doc in enumerate(anchors, start=1):
            lines.append(_format_anchor_source_line(i, doc))
        return "\n".join(lines)

    # Preserve order from source_indices while removing duplicates/invalid values.
    seen: set[int] = set()
    valid_indices: List[int] = []
    for idx in source_indices:
        if idx in seen:
            continue
        if 1 <= idx <= len(anchors):
            seen.add(idx)
            valid_indices.append(idx)

    if not valid_indices:
        return "**Fontes:** (nenhuma fonte citada no corpo)"

    for idx in valid_indices:
        lines.append(_format_anchor_source_line(idx, anchors[idx - 1]))

    return "\n".join(lines)


def count_citations_in_answer(answer: str) -> int:
    """Count how many [Fonte N] references appear in an answer string."""
    return len(re.findall(r"\[Fonte\s*\d+\]", answer, re.IGNORECASE))


def max_citation_index(answer: str) -> int:
    """Return the highest [Fonte N] index referenced in the answer, or 0."""
    matches = re.findall(r"\[Fonte\s*(\d+)\]", answer, re.IGNORECASE)
    if not matches:
        return 0
    return max(int(m) for m in matches)
