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


def count_citations_in_answer(answer: str) -> int:
    """Count how many [Fonte N] references appear in an answer string."""
    return len(re.findall(r"\[Fonte\s*\d+\]", answer, re.IGNORECASE))


def max_citation_index(answer: str) -> int:
    """Return the highest [Fonte N] index referenced in the answer, or 0."""
    matches = re.findall(r"\[Fonte\s*(\d+)\]", answer, re.IGNORECASE)
    if not matches:
        return 0
    return max(int(m) for m in matches)
