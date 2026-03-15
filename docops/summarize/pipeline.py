"""Multi-step deep summary pipeline for DocOps Agent.

Flow:
    1. collect_ordered_chunks  — fetch ALL document chunks without query ranking,
                                  sorted by document order (chunk_index / page).
    2. clean_chunks            — normalize encoding artifacts in chunk texts.
    3. group_chunks            — cluster chunks into logical sections or windows.
    4. summarize_groups        — generate a partial summary per group (LLM call × N).
    5. consolidate_summaries   — merge partials into a global analytical view (1 call).
    6. select_citation_anchors — pick one representative chunk per group (up to
                                  SUMMARY_MAX_SOURCES). These become the SINGLE
                                  source of truth for both the synthesis context
                                  and the final Fontes: section, ensuring [Fonte N]
                                  in the body always corresponds to [Fonte N] in the
                                  sources list.
    6b. finalize_deep_summary  — produce the structured deep-summary draft (1 call),
                                  using the citation_anchors as context.
    6c. polish_deep_summary_style — rewrite the draft into a more cohesive,
                                  study-friendly explanation (1 call).
    6d. validate_summary_citations — check [Fonte N] references in the final text,
                                  remove phantom citations (N > len(anchors)), log
                                  whether inline citations are present.
    6e. validate_summary_grounding — split final text into paragraph blocks; for
                                  each block with citations, compute token overlap
                                  with the cited anchor texts; flag (and optionally
                                  LLM-repair) blocks below threshold. Repair is off
                                  by default (SUMMARY_GROUNDING_REPAIR=false) and
                                  only runs for clearly weak overlaps.
    7. clean_output            — light normalization of the LLM output.
    8. build_anchor_sources_section — append Fontes: built from the SAME
                                  citation_anchors, with richer location display
                                  (file > section > page range) and strict 1:1
                                  numbering so [Fonte N] in the body maps exactly
                                  to entry N in the sources section.

The pipeline treats the target document as a *closed, ordered corpus*, not as
a relevance-ranked open search. This is the key difference from the QA flow.
"""

from __future__ import annotations

from typing import Any
import unicodedata
import time

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from docops.config import config
from docops.llm.content import response_text
from docops.llm.router import build_chat_model
from docops.logging import get_logger
import re

from docops.ingestion.pdf_structure import infer_pdf_structure, extract_pdf_outline
from docops.rag.citations import build_context_block, build_anchor_sources_section
from docops.rag.prompts import (
    DEEP_SUMMARY_DEOVERREACH_PROMPT,
    DEEP_SUMMARY_MICRO_BACKFILL_PROMPT,
    DEEP_SUMMARY_PARTIAL_PROMPT,
    DEEP_SUMMARY_CONSOLIDATE_PROMPT,
    DEEP_SUMMARY_FINAL_PROMPT,
    DEEP_SUMMARY_RESYNTHESIS_PROMPT,
    DEEP_SUMMARY_STRUCTURE_FIX_PROMPT,
    DEEP_SUMMARY_STYLE_POLISH_PROMPT,
    DEEP_SUMMARY_TOPIC_BACKFILL_PROMPT,
    SUMMARY_BLOCK_REPAIR_PROMPT,
    SYSTEM_PROMPT,
)
from docops.summarize.coverage_profiles import resolve_coverage_profile
from docops.summarize.outline import (
    extract_document_topics,
    score_topic_outline_coverage,
    get_topic_anchors,
)
from docops.summarize.text_cleaner import clean_chunk_text, clean_summary_output

logger = get_logger("docops.summarize.pipeline")

# ── Tuning constants ──────────────────────────────────────────────────────────
# These can be overridden via environment variables through docops.config:
#   SUMMARY_GROUP_SIZE  (default 8)  — chunks per partial-summary group
#   SUMMARY_MAX_GROUPS  (default 6)  — max groups = max partial LLM calls
#   SUMMARY_SECTION_THRESHOLD (default 0.7) — min fraction of chunks with
#     section metadata required to use section-based grouping

# Module-level defaults used when config values are not available.
SUMMARY_GROUP_SIZE: int = 8
SUMMARY_MAX_GROUPS: int = 6
SECTION_COVERAGE_THRESHOLD: float = 0.7


def _get_tuning() -> tuple[int, int, float]:
    """Return (group_size, max_groups, section_threshold) from config or defaults."""
    try:
        return (
            config.summary_group_size,
            config.summary_max_groups,
            config.summary_section_threshold,
        )
    except AttributeError:
        # Graceful fallback if config properties are not yet available
        return SUMMARY_GROUP_SIZE, SUMMARY_MAX_GROUPS, SECTION_COVERAGE_THRESHOLD


# ── LLM factory ──────────────────────────────────────────────────────────────

def _get_llm(route: str = "complex", temperature: float = 0.2):
    return build_chat_model(route=route, temperature=temperature)


# ── Step 1: collect all chunks in document order ─────────────────────────────

def collect_ordered_chunks(
    doc_name: str,
    doc_id: str,
    user_id: int,
) -> list[Document]:
    """Fetch ALL chunks for a document and return them sorted by document order.

    Uses Chroma's ``get()`` API (no query embedding) when available, so that
    retrieval does not depend on relevance ranking. Falls back to a high-k
    similarity search when ``get()`` is unavailable.

    Sort order: chunk_index → page_start → page → page_end (ascending).
    """
    from docops.ingestion.indexer import get_vectorstore_for_user

    vs = get_vectorstore_for_user(user_id)
    where_filter: dict = {"doc_id": doc_id} if doc_id else {"file_name": doc_name}

    # Primary path: use Chroma get() — no query, no ranking bias
    try:
        raw = vs.get(where=where_filter, include=["documents", "metadatas"])
        ids: list[str] = raw.get("ids") or []
        documents: list[str] = raw.get("documents") or []
        metadatas: list[dict] = raw.get("metadatas") or []

        if ids:
            chunks = [
                Document(page_content=doc_text or "", metadata=meta or {})
                for doc_text, meta in zip(documents, metadatas)
            ]
            sorted_chunks = _sort_chunks(chunks)
            logger.info(
                "Collected %d chunks for doc_id=%s via Chroma get() "
                "(sort: chunk_index → page_start → page_end).",
                len(sorted_chunks),
                doc_id,
            )
            return sorted_chunks

        logger.info(
            "Chroma get() returned no results for doc_id=%s; trying fallback.", doc_id
        )
    except Exception as exc:
        logger.warning("Chroma get() failed (%s); falling back to similarity_search.", exc)

    # Fallback: high-k similarity search + sort
    return _fallback_collect(doc_name, doc_id, user_id)


def _fallback_collect(doc_name: str, doc_id: str, user_id: int) -> list[Document]:
    """Fallback chunk collection via similarity_search with a large k."""
    from docops.rag.retriever import retrieve_for_doc

    chunks = retrieve_for_doc(
        doc_name,
        query="conteúdo completo do documento",
        top_k=500,
        user_id=user_id,
        doc_id=doc_id,
    )
    logger.info(
        "Collected %d chunks for '%s' via fallback similarity_search.", len(chunks), doc_name
    )
    return _sort_chunks(chunks)


def _sort_chunks(chunks: list[Document]) -> list[Document]:
    """Sort chunks by document order using available metadata."""

    def _sort_key(doc: Document) -> tuple[int, int, int]:
        meta = doc.metadata
        raw_ci = meta.get("chunk_index"); chunk_index = int(raw_ci) if raw_ci is not None else 999_999
        page_start = int(meta.get("page_start") or meta.get("page") or 0)
        page_end = int(meta.get("page_end") or page_start)
        return (chunk_index, page_start, page_end)

    return sorted(chunks, key=_sort_key)


# ── Step 2: clean chunk texts ─────────────────────────────────────────────────

def _clean_chunks(chunks: list[Document]) -> list[Document]:
    """Return new Document objects with cleaned page_content."""
    cleaned = []
    for doc in chunks:
        new_content = clean_chunk_text(doc.page_content)
        cleaned.append(Document(page_content=new_content, metadata=doc.metadata))
    return cleaned


# ── Step 3: group chunks into logical blocks ──────────────────────────────────

def group_chunks(
    chunks: list[Document],
    infer_pdf: bool = True,
) -> list[list[Document]]:
    """Cluster chunks into logical groups for partial summarization.

    Grouping rule:
    - **PDF structure inference**: when chunks are PDFs without section metadata,
      try to infer structure first, then use section-based grouping.
    - **Section-based**: used when ≥ SUMMARY_SECTION_THRESHOLD of chunks carry
      ``section_path`` or ``section_title`` metadata. Consecutive chunks that
      share the same section key form one group.
    - **Topic-transition**: for weakly structured PDFs, detect topic transitions
      instead of blind fixed windows.
    - **Window-based** (final fallback): fixed-size windows of SUMMARY_GROUP_SIZE chunks.

    The result is capped at SUMMARY_MAX_GROUPS by merging the two smallest
    adjacent groups iteratively until the cap is reached.
    """
    if not chunks:
        return []

    group_size, max_groups, section_threshold = _get_tuning()

    # Count chunks with meaningful section metadata BEFORE inference.
    has_section_before = sum(
        1
        for c in chunks
        if c.metadata.get("section_path") or c.metadata.get("section_title")
    )
    coverage_before = has_section_before / len(chunks) if chunks else 0.0

    # Try PDF structure inference if most chunks lack section metadata.
    pdf_inference_applied = False
    if infer_pdf and coverage_before < section_threshold:
        pdf_chunks = [
            c for c in chunks
            if str(c.metadata.get("file_type", "")).lower() == "pdf"
        ]
        if pdf_chunks and len(pdf_chunks) / len(chunks) >= 0.5:
            infer_pdf_structure(chunks)
            pdf_inference_applied = True

    # Recount after inference.
    has_section = sum(
        1
        for c in chunks
        if c.metadata.get("section_path") or c.metadata.get("section_title")
    )
    coverage = has_section / len(chunks)
    use_sections = coverage >= section_threshold

    if use_sections:
        groups = _group_by_section(chunks)
        method = "section-based"
        if pdf_inference_applied:
            method = "section-based (PDF structure inferred)"
        logger.info(
            "Grouping rule: %s (%.0f%% of chunks have section metadata) "
            "→ %d section groups from %d chunks.",
            method,
            coverage * 100,
            len(groups),
            len(chunks),
        )
    elif pdf_inference_applied and coverage > 0:
        # Partial inference succeeded — use section-based with lower threshold.
        groups = _group_by_section(chunks)
        logger.info(
            "Grouping rule: section-based with partial PDF inference "
            "(%.0f%% coverage, below threshold=%.0f%% but inference enriched) "
            "→ %d groups from %d chunks.",
            coverage * 100,
            section_threshold * 100,
            len(groups),
            len(chunks),
        )
    else:
        # Fallback: topic-transition grouping for PDFs, else window-based.
        groups = _group_by_topic_transition(chunks, group_size)
        if groups and len(groups) != len(range(0, len(chunks), group_size)):
            logger.info(
                "Grouping rule: topic-transition (%.0f%% section coverage) "
                "→ %d groups from %d chunks.",
                coverage * 100,
                len(groups),
                len(chunks),
            )
        else:
            groups = _group_by_window(chunks, group_size)
            logger.info(
                "Grouping rule: window-based (only %.0f%% of chunks have section metadata, "
                "threshold=%.0f%%) → %d windows from %d chunks (window_size=%d).",
                coverage * 100,
                section_threshold * 100,
                len(groups),
                len(chunks),
                group_size,
            )

    return _normalize_groups(groups, max_groups)


def _group_by_section(chunks: list[Document]) -> list[list[Document]]:
    """Group consecutive chunks that share the same section path."""
    groups: list[list[Document]] = []
    current_section: str | None = None
    current_group: list[Document] = []

    for chunk in chunks:
        meta = chunk.metadata
        section = meta.get("section_path") or meta.get("section_title") or ""

        if section != current_section:
            if current_group:
                groups.append(current_group)
            current_group = [chunk]
            current_section = section
        else:
            current_group.append(chunk)

    if current_group:
        groups.append(current_group)

    return groups


def _group_by_window(
    chunks: list[Document],
    group_size: int = SUMMARY_GROUP_SIZE,
) -> list[list[Document]]:
    """Group chunks into fixed-size windows of ``group_size`` chunks."""
    return [
        chunks[i: i + group_size]
        for i in range(0, len(chunks), group_size)
    ]


def _group_by_topic_transition(
    chunks: list[Document],
    max_group_size: int = SUMMARY_GROUP_SIZE,
    transition_threshold: float = 0.70,
) -> list[list[Document]]:
    """Group chunks by detecting lexical topic transitions.

    Starts a new group when the word overlap between consecutive chunks
    drops below the threshold, indicating a topic shift. Groups are capped
    at max_group_size to prevent oversized groups in monotopic documents.

    Falls back to window-based if no transitions are detected.
    """
    if not chunks:
        return []
    if len(chunks) <= max_group_size:
        return [chunks]

    groups: list[list[Document]] = []
    current_group: list[Document] = [chunks[0]]

    for i in range(1, len(chunks)):
        prev_text = (chunks[i - 1].page_content or "").strip()
        curr_text = (chunks[i].page_content or "").strip()

        # Compute word overlap.
        prev_words = set(re.findall(r"\w{3,}", prev_text.lower()))
        curr_words = set(re.findall(r"\w{3,}", curr_text.lower()))

        if prev_words and curr_words:
            overlap = len(prev_words & curr_words) / len(prev_words | curr_words)
        else:
            overlap = 0.0

        is_transition = overlap < (1.0 - transition_threshold)
        at_max_size = len(current_group) >= max_group_size

        if is_transition or at_max_size:
            groups.append(current_group)
            current_group = [chunks[i]]
        else:
            current_group.append(chunks[i])

    if current_group:
        groups.append(current_group)

    return groups


def _normalize_groups(
    groups: list[list[Document]],
    max_groups: int = SUMMARY_MAX_GROUPS,
) -> list[list[Document]]:
    """Remove empty groups and cap at ``max_groups`` by merging smallest pairs."""
    groups = [g for g in groups if g]

    # Merge adjacent groups until we are at or below the cap
    while len(groups) > max_groups:
        # Find the pair of adjacent groups with the smallest combined size
        merge_idx = min(
            range(len(groups) - 1),
            key=lambda i: len(groups[i]) + len(groups[i + 1]),
        )
        merged = groups[merge_idx] + groups[merge_idx + 1]
        groups = groups[:merge_idx] + [merged] + groups[merge_idx + 2:]

    return groups


# ── Step 4: partial summaries ─────────────────────────────────────────────────

def summarize_groups(
    groups: list[list[Document]],
    doc_name: str,
    llm,
) -> list[str]:
    """Generate one partial summary per chunk group.

    Returns a list of strings, one per group, labelled by section.
    On LLM failure for a group the raw context excerpt is used as fallback.
    """
    partials: list[str] = []

    for i, group in enumerate(groups, start=1):
        section_label = (
            group[0].metadata.get("section_path")
            or group[0].metadata.get("section_title")
            or f"Parte {i}"
        )
        context = build_context_block(group)
        prompt = DEEP_SUMMARY_PARTIAL_PROMPT.format(
            doc_name=doc_name,
            section_label=section_label,
            context=context,
        )

        try:
            response = llm.invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
            )
            partial_text = response_text(response)
            logger.debug("Partial summary %d/%d done (%d chars).", i, len(groups), len(partial_text))
        except Exception as exc:
            logger.warning("Partial summary for group %d failed: %s", i, exc)
            # Fallback: excerpt from the context block
            partial_text = f"(Resumo parcial indisponível — erro no LLM: {exc})"

        partials.append(f"### {section_label}\n{partial_text}")

    return partials


# ── Step 5: consolidation ─────────────────────────────────────────────────────

def consolidate_summaries(
    partials: list[str],
    doc_name: str,
    llm,
) -> str:
    """Merge all partial summaries into a single analytical overview."""
    partials_block = "\n\n---\n\n".join(partials)
    prompt = DEEP_SUMMARY_CONSOLIDATE_PROMPT.format(
        doc_name=doc_name,
        partials_block=partials_block,
    )

    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        consolidated = response_text(response)
        logger.debug("Consolidation done (%d chars).", len(consolidated))
        return consolidated
    except Exception as exc:
        logger.warning("Consolidation failed: %s", exc)
        # Fallback: concatenate partials as the consolidated view
        return "\n\n".join(partials)


# ── Citation validation ───────────────────────────────────────────────────────

# Pattern matching [Fonte N] or [fonte n] (case-insensitive)
_CITATION_RE = re.compile(r"\[Fonte\s*(\d+)\]", re.IGNORECASE)
_SOURCES_SECTION_RE = re.compile(
    r"\n{0,2}(?:\*\*Fontes:\*\*|#+\s*Fontes:?)\s*[\s\S]*$",
    re.IGNORECASE,
)
_INLINE_SOURCES_LINE_RE = re.compile(
    r"^\s*(?:\*\*)?Fontes?\s*:\s*.*$",
    re.IGNORECASE,
)
_SOURCE_MAPPING_LINE_RE = re.compile(
    r"^\s*(?:-+\s*)?\[Fonte\s*\d+\]\s*:\s*.*$",
    re.IGNORECASE,
)
_SOURCE_BULLET_LINE_RE = re.compile(
    r"^\s*-\s*\[Fonte\s*\d+\].*$",
    re.IGNORECASE,
)
_ORPHAN_CITATION_LINE_RE = re.compile(
    r"^\s*(?:\[\s*Fonte\s*\d+\s*\]\s*)+$",
    re.IGNORECASE,
)
_SOURCE_LABEL_LINE_RE = re.compile(
    r"^\s*(?:-+\s*)?(?:\[)?Fonte\s*\d+(?:\])?\s*(?::\s*.*)?(?:[.\-–—]\s*)?$",
    re.IGNORECASE,
)
_REPAIR_META_LINE_RE = re.compile(
    r"^\s*(não encontrei informações(?: nas fontes fornecidas)?|"
    r"não foi possível reescrever(?: o bloco)?(?: com base nas? fontes? fornecidas?)?|"
    r"as fontes(?: fornecidas)? tratam de|"
    r"para reescrever o bloco|"
    r"seria necessário fornecer documentos?)\b.*$",
    re.IGNORECASE,
)
_META_HEADER_RE = re.compile(
    r"^\s*\[meta\][^\n]*\n?",
    re.IGNORECASE,
)

# Source dump lines: [Fonte N] used as list entries leaked into the body
# (not as inline citations within prose).
#
# Type 1 — multiple sequential [Fonte N] at the START of a line:
#   e.g., "[Fonte 1] ... [Fonte 2] ..." or "[Fonte 1] texto [Fonte 2] texto"
#   Key invariant: line begins with [Fonte N], ruling out prose like
#   "Como [Fonte 1] e [Fonte 2] mostram, ..." (starts with "Como").
_SOURCE_DUMP_MULTI_RE = re.compile(
    r"^\s*\[\s*Fonte\s*\d+\s*\][^\[\n]{0,60}(?:\[\s*Fonte\s*\d+\s*\])+",
    re.IGNORECASE,
)

# Type 2 — single [Fonte N] at the START of a line followed by file/page metadata
#   (matches the build_anchor_sources_section output format that leaks into the body):
#   e.g., "[Fonte 1] doc.pdf (página 3)" or "[Fonte 1] **doc.pdf** > p. 5"
_SOURCE_DUMP_ENTRY_RE = re.compile(
    r"^\s*\[\s*Fonte\s*\d+\s*\][^,\n]{0,120}"
    r"(?:página|pág\.|>\s*p\.|>\s*pp\.|\bp\.\s*\d|\bpp\.\s*\d"
    r"|\.(?:pdf|txt|md|docx|xlsx|csv)\b)"
    r"[^\n]*$",
    re.IGNORECASE,
)

# Non-canonical citation pattern: bracketed text that is NOT [Fonte N].
# Matches things like [Contexto adicional, p. 4], [meta], [Fonte extra 2],
# but must NOT match valid citations [Fonte 1], mathematical intervals like
# [0,1] or [a,b], or Markdown link syntax [text](url).
# Rules:
#   - Must start with a letter (not a digit or Fonte)
#   - OR start with "Fonte " but not followed by a lone integer
#   - Must NOT be followed by "(" (Markdown link) — that would be [text](url)
_NON_CANONICAL_CITATION_RE = re.compile(
    r"\["
    r"(?!"                              # negative lookahead: skip valid patterns
    r"Fonte\s+\d+\]"                   # canonical [Fonte N]
    r"|"
    r"\d[\d.,]*\]"                     # numeric/math: [0,1], [3.14], [42]
    r")"
    r"(?:[A-Za-zÀ-ÿ][^\]\n]{1,80})"   # non-empty text starting with letter
    r"\]"
    r"(?!\()",                          # not Markdown link [text](url)
    re.IGNORECASE,
)


def _sanitize_non_canonical_citations(text: str) -> str:
    """Remove bracketed citations that are not of the canonical form [Fonte N].

    Preserves:
    - Valid inline citations: [Fonte 1], [Fonte 12]
    - Mathematical / numeric brackets: [0,1], [3.14], [0, 1]
    - Markdown links: [text](url)

    Removes:
    - [Contexto adicional, p. 4], [meta], [Fonte extra 2], etc.
    """
    if not text:
        return text
    return _NON_CANONICAL_CITATION_RE.sub("", text)


# Guardrail for repair step: broad citation fan-out blocks are usually too
# heterogeneous to rewrite safely in a single constrained pass.
MAX_REPAIR_CITATIONS_PER_BLOCK = 3

_SECTION_HEADING_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_SECTION_HEADING_H3_RE = re.compile(r"(?m)^###\s+(.+?)\s*$")
_ARTIFACT_CHAR_RE = re.compile(r"[\ufffd\ufb00-\ufb06\u0d80-\u0dff\ue000-\uf8ff]")

# Required deep-summary intent categories (heading-level, fuzzy match by keywords).
# We use intent categories (instead of exact title strings) to remain robust to
# small naming variations such as "Panorama Geral" vs "Objetivo e Contexto".
_REQUIRED_SECTION_CATEGORIES: dict[str, tuple[str, ...]] = {
    "overview": (
        "objetiv", "context", "panorama", "visao", "introducao",
        "escopo", "motivacao", "proposito", "apresentacao",
    ),
    "logic": (
        "linha log", "constru", "fundament", "estrutura",
        "organizacao", "encadeamento", "arquitetura", "fluxo",
        "metodologi", "metodo", "topico", "roteiro",
    ),
    "concepts": (
        "conceit", "defin", "term", "principi", "teoria",
        "fundamento", "nocion", "nocao", "base teoric",
        "referencial", "conceitual",
    ),
    "closure": (
        "sinte", "conclus", "aplic", "variac", "considerac",
        "resultado", "discuss", "fechamento", "resumo final",
        "contribuic",
    ),
}

# Body-level fallback patterns used when heading keywords are missing.
# This reduces false negatives for summaries that keep concepts integrated in
# broader sections (common in PDF-heavy technical content).
_SECTION_BODY_FALLBACK_PATTERNS: dict[str, re.Pattern[str]] = {
    "overview": re.compile(
        r"\b(?:objetiv\w*|context\w*|escop\w*|proposit\w*|motivac\w*|introduc\w*|propoe\w*|visa\w*)\b",
        re.IGNORECASE,
    ),
    "logic": re.compile(
        r"\b(?:linha\s+log\w*|encade\w*|organiz\w*|estrutura\w*|metodolog\w*|sequenc\w*|process\w*|fluxo\w*|passo\w*)\b",
        re.IGNORECASE,
    ),
    "concepts": re.compile(
        r"\b(?:conceit\w*|defin\w*|fundament\w*|entrop\w*|gini\w*|overfitting\w*|regulariz\w*|dimensao\s+vc|ganho\s+de\s+inform\w*)\b",
        re.IGNORECASE,
    ),
    "closure": re.compile(
        r"\b(?:sintese\w*|conclus\w*|resultado\w*|considerac\w*|fechament\w*|resumo\s+final|contribuic\w*)\b",
        re.IGNORECASE,
    ),
}

# ── Coverage gate: signal detection patterns ──────────────────────────────────
#
# These patterns detect *content signal types* in source chunks (not in summaries).
# A signal type is considered "present" when at least one chunk matches.
#
# Formula/math signals: Greek letters, math operators, LaTeX macros, basic
#   algebraic patterns (x = y, x^2), complexity notation O(n), ASCII math,
#   subscripts, argmin/min/sum/log notation, cardinality, Greek names as words.
_COVERAGE_FORMULA_SIGNAL_RE = re.compile(
    r"[α-ωΑ-Ωα-ω∑∫∏√∞±×÷≤≥≠≈∂∇]"
    r"|\\(?:frac|sum|int|sigma|theta|alpha|beta|gamma|delta|mu|nu|lambda|pi|phi|psi|omega"
    r"|epsilon|zeta|eta|iota|kappa|xi|rho|tau|upsilon|chi)\b"
    r"|\b[a-zA-Z]\s*=\s*[^=\s\n]"
    r"|\b\d+\s*[\+\-\*\/]\s*\d"
    r"|[a-zA-Z]\s*\^\s*\d"
    r"|\bO\s*\(\s*[^\)]+\)"
    r"|\bσ\b|\bμ\b|\bλ\b|\bθ\b|\bδ\b|\bε\b"
    # ASCII math: argmin, argmax, min, max, sum, log, ln, exp, etc.
    r"|\b(?:argmin|argmax|min|max|sum|log2?|ln|exp|sqrt|prob)\s*[({[]"
    # Subscript notation: x_i, p_k, H(S), R(t), etc.
    r"|[a-zA-Z]_[a-zA-Z0-9{]"
    # Cardinality: |T|, |S|, |N|
    r"|\|\s*[A-Za-z][A-Za-z0-9]*\s*\|"
    # Greek names written as words (PT-BR + EN)
    r"|\b(?:alpha|alfa|beta|gamma|gama|delta|epsilon|theta|teta|lambda|sigma|omega|phi|psi|pi)\b"
    # Fraction-like patterns: a/b where both are short
    r"|\b[a-zA-Z]\s*/\s*[a-zA-Z]\b",
    re.UNICODE | re.IGNORECASE,
)

# Procedure/algorithm signals: explicit step markers, numbered-list action items,
#   procedural vocabulary.
_COVERAGE_PROCEDURE_SIGNAL_RE = re.compile(
    r"\b(?:passo|etapa|step|fase)\s+\d"
    r"|\b(?:algoritmo|procedimento|protocolo|fluxograma)\b"
    r"|\b(?:primeiro|segundo|terceiro|quarto|quinto)\s+(?:passo|ponto|item)\b"
    r"|^\s*\d+[\.\)]\s+\w",
    re.IGNORECASE | re.MULTILINE,
)

# Example signals: explicit example markers, illustrative vocabulary.
_COVERAGE_EXAMPLE_SIGNAL_RE = re.compile(
    r"\b(?:exemplo|por exemplo)\b"
    r"|e\.g\.|i\.e\."
    r"|\bex\.:?"
    r"|\b(?:ilustra[çc][aã]o|demonstra[çc][aã]o|caso pr[aá]tico|caso de uso)\b"
    r"|\b(?:considere|suponha|imagine)\b",
    re.IGNORECASE,
)

# Concept/definition signals: bold terms (markdown), definitional phrases,
# title-like lines in PDFs/slides, colon-definitions, and list-based concepts.
_COVERAGE_CONCEPT_SIGNAL_RE = re.compile(
    r"\*\*[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{2,29}\*\*"
    r"|\b(?:defini[çc][aã]o de|conceito de|denomina-se|denomina\s+se"
    r"|[eé] definid[oa] como|se define como|chama-se)\b"
    r"|\b(?:no[çc][aã]o de|nomenclatura|terminologia|glossário)\b"
    # Colon-definition patterns (common in slides): "Term: description"
    r"|^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑa-záàâãéêíóôõúçñ][A-Za-zÀ-ÿ\s\-]{2,40}:\s+[A-Za-zÀ-ÿ]"
    # "is defined as", "refers to", "means" (EN)
    r"|\b(?:is\s+defined\s+as|refers?\s+to|(?:it\s+)?means|is\s+called|known\s+as)\b"
    # "consiste em", "refere-se a", "significa" (PT-BR)
    r"|\b(?:consiste\s+em|refere-se\s+a|significa|corresponde\s+a)\b"
    # Short ALL-CAPS terms (≥3 chars, common in slides as concept titles)
    # Use (?-i:...) to locally disable IGNORECASE so only actual uppercase matches.
    r"|(?-i:(?:^|\s)[A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑ]{3,25}(?:\s|$))"
    # Bullet/numbered list items that introduce concepts
    r"|(?:^|\n)\s*(?:[-•]\s+|[0-9]+[.)]\s+)[A-ZÁÀÂÃÉÊÍÓÔÕÚÇÑa-záàâãéêíóôõúçñ].{5,40}:",
    re.IGNORECASE | re.MULTILINE,
)

# ── Coverage gate: summary coverage detection patterns ────────────────────────
#
# These patterns detect whether the *final summary* discusses each signal type.
# Used by score_coverage() to compute per-type coverage scores.

_COVERAGE_FORMULA_SUMMARY_RE = re.compile(
    r"\b(?:f[oó]rmula|equa[çc][aã]o|c[áa]lculo|express[aã]o|nota[çc][aã]o"
    r"|definid[oa] por|representad[oa] por|dad[oa] por|proporcional|coeficiente)\b"
    r"|[α-ωΑ-Ωα-ω∑∫∏√∞±∂∇]"
    r"|\b(?:matem[aá]tic|[aá]lgebr|fun[çc][aã]o|vari[aá]vel|par[aâ]metro)\b"
    # ASCII math notation in summaries
    r"|\b(?:argmin|argmax|log2?|ln|exp|sqrt|somat[oó]rio|summation)\b"
    r"|[a-zA-Z]_[a-zA-Z0-9{]"
    r"|\|\s*[A-Za-z][A-Za-z0-9]*\s*\|"
    # Greek names as words
    r"|\b(?:alpha|alfa|beta|gamma|gama|delta|epsilon|theta|teta|lambda|sigma|omega)\b",
    re.IGNORECASE,
)

_COVERAGE_PROCEDURE_SUMMARY_RE = re.compile(
    r"\b(?:algoritmo|passo|etapa|procedimento|m[eé]todo|processo"
    r"|sequ[eê]ncia|protocolo|fluxo|roteiro|etapas)\b",
    re.IGNORECASE,
)

_COVERAGE_EXAMPLE_SUMMARY_RE = re.compile(
    r"\b(?:exemplo|por exemplo|ilustra|demonstra|mostra|evidencia|caso)\b",
    re.IGNORECASE,
)

_COVERAGE_CONCEPT_SUMMARY_RE = re.compile(
    r"\b(?:conceito|defini[çc][aã]o|denominad|termo|no[çc][aã]o|nomenclatura"
    r"|concept|definition|fundament\w+|princip\w+|propriedad\w+|caracter[ií]stic\w+"
    r"|abordagem|approach|framework|paradigm\w+|modelo\s+(?:de|para)|model\s+(?:of|for))\b",
    re.IGNORECASE,
)


_FACET_ORDER: tuple[str, ...] = (
    "objective_context",
    "procedural_construction",
    "math_formulas",
    "examples_applications",
    "validation_and_tuning",
    "complexity_generalization",
)

_FACET_LABELS: dict[str, str] = {
    "objective_context": "Objetivo/Contexto",
    "procedural_construction": "Processo/Algoritmo de construÃ§Ã£o",
    "math_formulas": "FÃ³rmulas/NotaÃ§Ã£o matemÃ¡tica",
    "examples_applications": "Exemplos/AplicaÃ§Ãµes",
    "validation_and_tuning": "ValidaÃ§Ã£o/Ajuste prÃ¡tico",
    "complexity_generalization": "Complexidade/GeneralizaÃ§Ã£o",
}

_FACET_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "objective_context": re.compile(
        r"\b(?:objetiv\w*|context\w*|escop\w*|introduc\w*|motivac\w*|propost\w*|familias?\s+de\s+aprendizado)\b",
        re.IGNORECASE,
    ),
    "procedural_construction": re.compile(
        r"\b(?:id3|heuristica|heurÃ­stica|algoritmo\s+guloso|particion\w*|passo\s+\d|etapa\s+\d|n[Ã³o]\s+folha)\b",
        re.IGNORECASE,
    ),
    "math_formulas": re.compile(
        _COVERAGE_FORMULA_SIGNAL_RE.pattern
        + r"|\b(?:entrop\w*|gini|impurez\w*|log2|argmin)\b",
        re.IGNORECASE | re.UNICODE,
    ),
    "examples_applications": re.compile(
        r"\b(?:exemplo|por exemplo|caso pr[aÃ¡]tico|caso de uso|classifica\w+|candidat\w+|atendimento telef[oÃ´]nico)\b",
        re.IGNORECASE,
    ),
    "validation_and_tuning": re.compile(
        r"\b(?:valida\w+|cross[-\s]?validation|scikit[-\s]?learn|cost_complexity_pruning_path|alpha_eff|hiperpar[aÃ¢]metr\w+)\b",
        re.IGNORECASE,
    ),
    "complexity_generalization": re.compile(
        r"\b(?:overfitting|generaliza\w+|dimens[aÃ£]o\s+vc|vapnik|chervonenkis|vc[-\s]?dimension|complexidad\w+)\b",
        re.IGNORECASE,
    ),
}

_BROKEN_FACET_SUMMARY_PATTERNS_BLOCK = r"""
_FACET_SUMMARY_PATTERNS: dict[str, re.Pattern[str]] = {
    "objective_context": re.compile(
        r"\b(?:objetiv\w*|context\w*|escop\w*|prop[Ãµo]e|motiva\w*|linha l[oÃ³]gica)\b",
        re.IGNORECASE,
    ),
    "procedural_construction": re.compile(
        r"\b(?:algoritmo|heur[Ã­i]stica|id3|passo|etapa|particion\w*|n[Ã³o]\s+folha|recursiv\w*)\b",
        re.IGNORECASE,
    ),
    "math_formulas": re.compile(
        r"\b(?:entrop\w*|gini|impurez\w*|f[oÃ³]rmula|log2|argmin|alpha|alfa|beta|gamma|delta)\b|[Î±-Ï‰Î‘-Î©Î±-Ï‰]",
        re.IGNORECASE | re.UNICODE,
    ),
    "examples_applications": re.compile(
        r"\b(?:exemplo|caso|aplica\w+|cen[aÃ¡]rio|classifica\w+|recrutamento|atendimento)\b",
        re.IGNORECASE,
    ),
    "validation_and_tuning": re.compile(
        r"\b(?:valida\w+|scikit|cost[-\s]?complexity|pruning|alpha_eff|parametr\w+|ajuste)\b",
        re.IGNORECASE,
    ),
    "complexity_generalization": re.compile(
        r"\b(?:overfitting|generaliza\w+|dimens[aÃ£]o\s+vc|vc[-\s]?dimension|complexidad\w+)\b",
        re.IGNORECASE,
    ),
}
"""

_GREEK_SYMBOL_RE = re.compile(r"[\u03B1-\u03C9\u0391-\u03A9]", re.UNICODE)

_FACET_SUMMARY_PATTERNS: dict[str, re.Pattern[str]] = {
    "objective_context": re.compile(
        r"\b(?:objetiv\w*|context\w*|escop\w*|propoe|motiva\w*|linha l[oó]gica)\b",
        re.IGNORECASE,
    ),
    "procedural_construction": re.compile(
        r"\b(?:algoritmo|heur[ií]stica|id3|passo|etapa|particion\w*|no\s+folha|recursiv\w*)\b",
        re.IGNORECASE,
    ),
    "math_formulas": re.compile(
        _COVERAGE_FORMULA_SUMMARY_RE.pattern
        + r"|\b(?:entrop\w*|gini|impurez\w*|formula|equacao|log2|argmin"
        + r"|alpha|alfa|beta|gamma|delta)\b"
        + r"|\|\s*[A-Za-z][A-Za-z0-9_]*\s*\|"
        + r"|[\u03B1-\u03C9\u0391-\u03A9]",
        re.IGNORECASE | re.UNICODE,
    ),
    "examples_applications": re.compile(
        r"\b(?:exemplo|caso|aplica\w+|cen[aá]rio|classifica\w+|recrutamento|atendimento)\b",
        re.IGNORECASE,
    ),
    "validation_and_tuning": re.compile(
        r"\b(?:valida\w+|scikit|cost[-\s]?complexity|pruning|alpha_eff|parametr\w+|ajuste)\b",
        re.IGNORECASE,
    ),
    "complexity_generalization": re.compile(
        r"\b(?:overfitting|generaliza\w+|dimens[aã]o\s+vc|vc[-\s]?dimension|complexidad\w+)\b",
        re.IGNORECASE,
    ),
}

_CRITICAL_FACETS: set[str] = {
    "procedural_construction",
    "math_formulas",
    "validation_and_tuning",
    "complexity_generalization",
}

_BROKEN_FORMULA_CONTEXT_BLOCK = r"""
_CARDINALITY_VAR_RE = re.compile(r"\|\s*([A-Za-z][A-Za-z0-9_]*)\s*\|")
_FORMULA_CONTEXT_LINE_RE = re.compile(
    r"(?:=|[+\-*/]|log2|argmin|somat[Ã³o]rio|cost[-\s]?complexity|r[_\s]*alpha|r\s*\(\s*t\s*\)|[Î±-Ï‰Î‘-Î©Î±-Ï‰])",
    re.IGNORECASE,
)


"""

_CARDINALITY_VAR_RE = re.compile(r"\|\s*([A-Za-z][A-Za-z0-9_]*)\s*\|")
_FORMULA_CONTEXT_LINE_RE = re.compile(
    r"(?:=|[+\-*/]|log2|argmin|somat[oó]rio|cost[-\s]?complexity|r[_\s]*alpha"
    r"|r\s*\(\s*t\s*\)|\|\s*[A-Za-z][A-Za-z0-9_]*\s*\||[\u03B1-\u03C9\u0391-\u03A9])",
    re.IGNORECASE,
)


def build_document_profile(
    chunks: list[Document],
    min_hits: int = 2,
) -> dict[str, Any]:
    """Build an evidence-first profile of topics/facets present in source chunks."""
    facet_hits: dict[str, int] = {facet: 0 for facet in _FACET_ORDER}
    facet_samples: dict[str, list[str]] = {facet: [] for facet in _FACET_ORDER}
    card_vars: set[str] = set()
    greek_symbols: set[str] = set()
    formula_lines = 0

    for chunk in chunks:
        text = (chunk.page_content or "").strip()
        if not text:
            continue

        card_vars.update(_CARDINALITY_VAR_RE.findall(text))
        greek_symbols.update(_GREEK_SYMBOL_RE.findall(text))
        if _FORMULA_CONTEXT_LINE_RE.search(text):
            formula_lines += 1

        for facet in _FACET_ORDER:
            pattern = _FACET_SIGNAL_PATTERNS[facet]
            if pattern.search(text):
                facet_hits[facet] += 1
                if len(facet_samples[facet]) < 2:
                    sample = re.sub(r"\s+", " ", text)[:180].strip()
                    if sample:
                        facet_samples[facet].append(sample)

    facets: dict[str, Any] = {}
    required_facets: list[str] = []
    for facet in _FACET_ORDER:
        hits = facet_hits[facet]
        present = hits > 0
        required = hits >= max(1, min_hits)
        facets[facet] = {
            "label": _FACET_LABELS[facet],
            "hits": hits,
            "present": present,
            "required": required,
            "samples": facet_samples[facet],
        }
        if required:
            required_facets.append(facet)

    critical_required = [f for f in required_facets if f in _CRITICAL_FACETS]
    return {
        "facets": facets,
        "required_facets": required_facets,
        "critical_required_facets": critical_required,
        "min_hits": max(1, min_hits),
        "notation": {
            "cardinality_vars": sorted(card_vars),
            "greek_symbols": sorted(greek_symbols),
            "formula_lines": formula_lines,
        },
    }


def _format_doc_profile_contract(profile: dict[str, Any]) -> str:
    """Render document-profile requirements as a compact prompt contract."""
    required = profile.get("required_facets", [])
    facets = profile.get("facets", {})
    notation = profile.get("notation", {})
    lines: list[str] = []
    # Defensive defaults to avoid accidental leakage from similarly named
    # feedback fields used in other helpers.
    topic_coverage_info = None
    notation_info = None
    critical_claims_info = None
    topic_coverage_min_score = 0.0
    notation_min_score = 0.0
    critical_claims_min_score = 0.0

    if required:
        lines.append("Facetas obrigatÃ³rias detectadas:")
        for facet in required:
            meta = facets.get(facet, {})
            lines.append(
                f"- {meta.get('label', facet)} (hits={int(meta.get('hits', 0))})"
            )
    else:
        lines.append(
            "Nenhuma faceta obrigatÃ³ria forte detectada; priorize cobertura equilibrada."
        )

    card_vars = notation.get("cardinality_vars", []) or []
    if card_vars:
        vars_block = ", ".join(f"|{v}|" for v in card_vars[:6])
        lines.append(f"NotaÃ§Ã£o de cardinalidade observada na fonte: {vars_block}.")
    if notation.get("greek_symbols"):
        syms = " ".join((notation.get("greek_symbols") or [])[:8])
        lines.append(f"SÃ­mbolos gregos observados na fonte: {syms}.")
    if topic_coverage_info is not None:
        topic_score = float(topic_coverage_info.get("overall_score", 1.0))
        lines.append(
            f"- topic/facet coverage: {topic_score:.2f} "
            f"(target >= {topic_coverage_min_score:.2f})"
        )
        missing_facets = topic_coverage_info.get("missing_facets", []) or []
        if missing_facets:
            labels = ", ".join(_FACET_LABELS.get(f, f) for f in missing_facets)
            lines.append(f"- facetas obrigatÃ³rias faltantes: {labels}")
    if notation_info is not None:
        notation_score = float(notation_info.get("score", 1.0))
        lines.append(
            f"- notation fidelity: {notation_score:.2f} "
            f"(target >= {notation_min_score:.2f})"
        )
        for issue in (notation_info.get("issues", []) or [])[:3]:
            lines.append(f"- notaÃ§Ã£o: {issue}")
    if critical_claims_info is not None:
        claim_score = float(critical_claims_info.get("score", 1.0))
        lines.append(
            f"- critical-claims coverage: {claim_score:.2f} "
            f"(target >= {critical_claims_min_score:.2f})"
        )
        missing_claims = critical_claims_info.get("missing_facets", []) or []
        if missing_claims:
            labels = ", ".join(_FACET_LABELS.get(f, f) for f in missing_claims)
            lines.append(f"- claims crÃ­ticos sem suporte citado: {labels}")
    return "\n".join(lines)


def _format_doc_profile_contract(profile: dict[str, Any]) -> str:
    """Render document-profile requirements as a compact prompt contract."""
    required = list(profile.get("required_facets", []) or [])
    facets = profile.get("facets", {}) or {}
    notation = profile.get("notation", {}) or {}
    lines: list[str] = []

    if required:
        lines.append("Facetas obrigatorias detectadas:")
        for facet in required:
            meta = facets.get(facet, {}) or {}
            lines.append(
                f"- {meta.get('label', _FACET_LABELS.get(facet, facet))} "
                f"(hits={int(meta.get('hits', 0))})"
            )
    else:
        lines.append(
            "Nenhuma faceta obrigatoria forte detectada; priorize cobertura equilibrada."
        )

    card_vars = list(notation.get("cardinality_vars", []) or [])
    if card_vars:
        vars_block = ", ".join(f"|{v}|" for v in card_vars[:6])
        lines.append(f"Notacao de cardinalidade observada na fonte: {vars_block}.")

    greek_symbols = list(notation.get("greek_symbols", []) or [])
    if greek_symbols:
        syms = " ".join(greek_symbols[:8])
        lines.append(f"Simbolos gregos observados na fonte: {syms}.")

    formula_lines = int(notation.get("formula_lines", 0) or 0)
    if formula_lines > 0:
        lines.append(f"Linhas com notacao/formulas detectadas na fonte: {formula_lines}.")

    lines.append(
        "Cada faceta obrigatoria deve aparecer de forma explicita com citacao inline [Fonte N]."
    )
    return "\n".join(lines)


def score_topic_coverage(final_text: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Score whether required document facets were explicitly covered in summary."""
    required = list(profile.get("required_facets", []))
    facet_scores: dict[str, float] = {}
    covered: list[str] = []
    missing: list[str] = []

    for facet in required:
        pattern = _FACET_SUMMARY_PATTERNS.get(facet)
        hits = len(pattern.findall(final_text)) if pattern else 0
        score = 1.0 if hits >= 1 else 0.0
        facet_scores[facet] = score
        if score >= 1.0:
            covered.append(facet)
        else:
            missing.append(facet)

    if required:
        overall = sum(facet_scores.values()) / len(required)
    else:
        overall = 1.0

    return {
        "overall_score": round(overall, 4),
        "required_facets": required,
        "covered_facets": covered,
        "missing_facets": missing,
        "facet_scores": facet_scores,
    }


def _assess_notation_fidelity_legacy(final_text: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Detect notation simplifications that may alter technical meaning."""
    notation = profile.get("notation", {})
    card_vars = list(notation.get("cardinality_vars", []))
    if not card_vars:
        return {
            "score": 1.0,
            "issues": [],
            "checked_vars": [],
            "active": False,
        }

    norm_text = _normalize_heading_for_match(final_text)
    lines = [line.strip() for line in final_text.splitlines() if line.strip()]
    checked_vars: list[str] = []
    issues: list[str] = []
    for var in card_vars:
        card_pat = re.compile(rf"\|\s*{re.escape(var)}\s*\|")
        var_pat = re.compile(rf"\b{re.escape(var)}\b", re.IGNORECASE)
        has_cardinality = bool(card_pat.search(final_text))
        has_formula_use = any(
            var_pat.search(line) and _FORMULA_CONTEXT_LINE_RE.search(line)
            for line in lines
        )
        if not has_formula_use:
            continue
        checked_vars.append(var)
        has_textual_cardinality = bool(
            re.search(
                rf"\b(?:numero|n[uú]mero|quantidade)\s+de\b[^\n]{{0,35}}\b{re.escape(var.lower())}\b",
                norm_text,
                re.IGNORECASE,
            )
        )
        if not has_cardinality and not has_textual_cardinality:
            issues.append(
                f"PossÃ­vel perda de cardinalidade para '{var}' (esperado |{var}| ou descriÃ§Ã£o equivalente)."
            )

    if not checked_vars:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (len(issues) / len(checked_vars)))

    return {
        "score": round(score, 4),
        "issues": issues,
        "checked_vars": checked_vars,
        "active": bool(checked_vars),
    }


def assess_notation_fidelity(final_text: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Detect notation simplifications and missing variable legends."""
    notation = profile.get("notation", {})
    card_vars = list(notation.get("cardinality_vars", []))
    require_legend = bool(getattr(config, "summary_notation_require_variable_legend", True))
    if not card_vars:
        return {
            "score": 1.0,
            "issues": [],
            "checked_vars": [],
            "missing_legends": [],
            "active": False,
            "legend_required": require_legend,
        }

    norm_text = _normalize_heading_for_match(final_text)
    lines = [line.strip() for line in final_text.splitlines() if line.strip()]
    checked_vars: list[str] = []
    issues: list[str] = []
    missing_legends: list[str] = []
    issue_vars: set[str] = set()

    for var in card_vars:
        var_escaped = re.escape(var)
        card_pat = re.compile(rf"\|\s*{var_escaped}\s*\|")
        var_pat = re.compile(rf"\b{var_escaped}\b", re.IGNORECASE)
        var_expr = rf"(?:\|\s*{var_escaped}\s*\||\b{var_escaped}\b)"
        has_cardinality = bool(card_pat.search(final_text))
        has_formula_use = any(
            var_pat.search(line) and _FORMULA_CONTEXT_LINE_RE.search(line)
            for line in lines
        )
        if not has_formula_use:
            continue

        checked_vars.append(var)
        has_textual_cardinality = bool(
            re.search(
                rf"\b(?:numero|n[uú]mero|quantidade)\s+de\b[^\n]{{0,50}}\b{re.escape(var.lower())}\b",
                norm_text,
                re.IGNORECASE,
            )
        )
        if not has_cardinality and not has_textual_cardinality:
            issues.append(
                f"Possivel perda de cardinalidade para '{var}' (esperado |{var}| ou descricao equivalente)."
            )
            issue_vars.add(var)

        if require_legend:
            has_legend = bool(
                re.search(
                    rf"\b(?:onde|sendo|em que|com)\b[^\n]{{0,140}}{var_expr}",
                    final_text,
                    re.IGNORECASE,
                )
                or re.search(
                    rf"{var_expr}\s*(?:representa|indica|denota|corresponde|significa|"
                    rf"refere[- ]?se|e\s+o\s+numero\s+de|e\s+a\s+quantidade\s+de)",
                    final_text,
                    re.IGNORECASE,
                )
            )
            if not has_legend:
                missing_legends.append(var)
                issues.append(
                    f"Variavel '{var}' aparece em notacao/formula sem legenda explicita."
                )
                issue_vars.add(var)

    if not checked_vars:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (len(issue_vars) / len(checked_vars)))

    return {
        "score": round(score, 4),
        "issues": issues,
        "checked_vars": checked_vars,
        "missing_legends": missing_legends,
        "active": bool(checked_vars),
        "legend_required": require_legend,
    }


def evaluate_critical_claim_coverage(
    final_text: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Verify that critical technical facets appear with inline citation support."""
    required = [
        facet for facet in profile.get("critical_required_facets", [])
        if facet in _FACET_SUMMARY_PATTERNS
    ]
    if not required:
        return {
            "score": 1.0,
            "required_facets": [],
            "supported_facets": [],
            "missing_facets": [],
        }

    paragraphs = [p for p in re.split(r"\n{2,}", final_text) if p.strip()]
    supported: list[str] = []
    missing: list[str] = []
    for facet in required:
        pat = _FACET_SUMMARY_PATTERNS[facet]
        found = any(pat.search(par) and _CITATION_RE.search(par) for par in paragraphs)
        if found:
            supported.append(facet)
        else:
            missing.append(facet)

    score = len(supported) / len(required) if required else 1.0
    return {
        "score": round(score, 4),
        "required_facets": required,
        "supported_facets": supported,
        "missing_facets": missing,
    }


_FACET_TO_SECTION_CATEGORY: dict[str, str] = {
    "objective_context": "overview",
    "procedural_construction": "logic",
    "math_formulas": "concepts",
    "examples_applications": "applications",
    "validation_and_tuning": "applications",
    "complexity_generalization": "closure",
}


def _best_anchor_for_facet(
    facet: str,
    citation_anchors: list[Document],
) -> tuple[int, str] | None:
    """Pick one anchor with direct lexical evidence for a target facet."""
    pat = _FACET_SIGNAL_PATTERNS.get(facet)
    if pat is None:
        return None
    for idx, anchor in enumerate(citation_anchors, start=1):
        text = (anchor.page_content or "").strip()
        if text and pat.search(text):
            return idx, text
    return None


def _make_claim_sentence(facet: str, anchor_idx: int, anchor_text: str) -> str:
    """Build one concise, cited claim sentence from a supporting anchor."""
    cleaned = re.sub(r"\s+", " ", anchor_text or "").strip()
    cleaned = _strip_inline_citations(cleaned)
    cleaned = cleaned[:240].rstrip(" ,;:")
    hint = {
        "procedural_construction": "O documento descreve explicitamente o procedimento de construcao do modelo.",
        "math_formulas": "O texto explicita criterios e notacao matematica para sustentar as decisoes do modelo.",
        "validation_and_tuning": "O material inclui validacao e ajuste pratico de parametros no fluxo de modelagem.",
        "complexity_generalization": "Tambem discute controle de complexidade e generalizacao para evitar overfitting.",
    }.get(facet, "O documento traz suporte tecnico explicito para este ponto.")
    if cleaned:
        return f"{hint} {cleaned} [Fonte {anchor_idx}]."
    return f"{hint} [Fonte {anchor_idx}]."


def _inject_claim_into_section(text: str, facet: str, sentence: str) -> str:
    """Inject one sentence into the most relevant existing section."""
    preamble, sections = _parse_sections(text)
    if not sections:
        return (text.rstrip() + "\n\n" + sentence).strip()

    target_category = _FACET_TO_SECTION_CATEGORY.get(facet, "concepts")
    target_keywords = _REQUIRED_SECTION_CATEGORIES.get(target_category, ())

    target_idx: int | None = None
    for idx, section in enumerate(sections):
        title_norm = _normalize_heading_for_match(section["title"])
        if any(k in title_norm for k in target_keywords):
            target_idx = idx
            break

    if target_idx is None:
        # Fallback: inject before closure if present, otherwise in middle section.
        closure_idx = next(
            (
                i for i, section in enumerate(sections)
                if any(
                    k in _normalize_heading_for_match(section["title"])
                    for k in _REQUIRED_SECTION_CATEGORIES.get("closure", ())
                )
            ),
            None,
        )
        if closure_idx is not None and closure_idx > 0:
            target_idx = max(0, closure_idx - 1)
        else:
            target_idx = min(len(sections) - 1, 2)

    body = sections[target_idx]["body"].strip()
    if sentence not in body:
        sections[target_idx]["body"] = f"{body}\n\n{sentence}".strip() if body else sentence

    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for section in sections:
        body = section["body"].strip()
        parts.append(f"## {section['title']}\n{body}" if body else f"## {section['title']}")
    return "\n\n".join(part for part in parts if part).strip()


def _repair_missing_critical_claims(
    text: str,
    missing_facets: list[str],
    citation_anchors: list[Document],
) -> tuple[str, dict[str, Any]]:
    """Repair missing critical-claim facets using deterministic local insertion."""
    if not missing_facets:
        return text, {"attempted": 0, "repaired": 0, "facets_repaired": []}

    current_text = text
    attempted = 0
    repaired = 0
    repaired_facets: list[str] = []

    for facet in missing_facets:
        support = _best_anchor_for_facet(facet, citation_anchors)
        if support is None:
            continue
        anchor_idx, anchor_text = support
        attempted += 1
        sentence = _make_claim_sentence(facet, anchor_idx, anchor_text)
        updated_text = _inject_claim_into_section(current_text, facet, sentence)
        if updated_text != current_text:
            current_text = updated_text
            repaired += 1
            repaired_facets.append(facet)

    return current_text, {
        "attempted": attempted,
        "repaired": repaired,
        "facets_repaired": repaired_facets,
    }


def compute_summary_rubric(
    *,
    structure_valid: bool,
    weak_ratio: float,
    unique_sources: int,
    min_unique_sources: int,
    coverage_score: float,
    facet_score: float,
    claims_score: float,
    notation_score: float,
    outline_score: float = 1.0,
) -> dict[str, float]:
    """Compute a compact multi-criterion quality rubric for final acceptance."""
    diversity_score = (
        1.0
        if min_unique_sources <= 0
        else min(1.0, unique_sources / max(1, min_unique_sources))
    )
    grounding_score = max(0.0, min(1.0, 1.0 - weak_ratio))
    structure_score = 1.0 if structure_valid else 0.0

    weights = {
        "structure": 0.15,
        "grounding": 0.15,
        "diversity": 0.10,
        "coverage": 0.10,
        "facets": 0.10,
        "outline": 0.20,
        "claims": 0.10,
        "notation": 0.05,
        "quality_penalty": 0.05,
    }
    # Quality penalty: if outline shows missing topics, apply a hard penalty.
    quality_penalty_score = 1.0 if outline_score >= 0.8 else outline_score

    overall = (
        structure_score * weights["structure"]
        + grounding_score * weights["grounding"]
        + diversity_score * weights["diversity"]
        + coverage_score * weights["coverage"]
        + facet_score * weights["facets"]
        + outline_score * weights["outline"]
        + claims_score * weights["claims"]
        + notation_score * weights["notation"]
        + quality_penalty_score * weights["quality_penalty"]
    )

    return {
        "structure_score": round(structure_score, 4),
        "grounding_score": round(grounding_score, 4),
        "diversity_score": round(diversity_score, 4),
        "coverage_score": round(coverage_score, 4),
        "facet_score": round(facet_score, 4),
        "outline_score": round(outline_score, 4),
        "claims_score": round(claims_score, 4),
        "notation_score": round(notation_score, 4),
        "overall_score": round(overall, 4),
    }


def _build_gap_contract(
    *,
    topic_coverage: dict[str, Any] | None = None,
    notation_info: dict[str, Any] | None = None,
    critical_claims: dict[str, Any] | None = None,
) -> str:
    """Create actionable gap list for re-synthesis prompt."""
    lines: list[str] = []
    if topic_coverage:
        missing = topic_coverage.get("missing_facets", []) or []
        if missing:
            labels = ", ".join(_FACET_LABELS.get(f, f) for f in missing)
            lines.append(f"- Cobertura temÃ¡tica faltante: {labels}.")
    if notation_info:
        issues = notation_info.get("issues", []) or []
        for issue in issues[:3]:
            lines.append(f"- NotaÃ§Ã£o/fidelidade: {issue}")
    if critical_claims:
        missing_claims = critical_claims.get("missing_facets", []) or []
        if missing_claims:
            labels = ", ".join(_FACET_LABELS.get(f, f) for f in missing_claims)
            lines.append(
                f"- Claims crÃ­ticos sem suporte citado explÃ­cito: {labels}."
            )
    if not lines:
        return "- Sem lacunas crÃ­ticas adicionais; priorize coesÃ£o, precisÃ£o e rastreabilidade."
    return "\n".join(lines)


def validate_summary_citations(
    text: str,
    citation_anchors: list[Document],
) -> tuple[str, dict]:
    """Validate and repair [Fonte N] citations in the final deep summary.

    This is the grounding/consistency check specific to the deep summary flow.
    It does not re-rank or re-retrieve — it validates structural coherence between
    the citation references in the body and the citation_anchors that will be
    rendered as the Fontes: section.

    Checks:
        1. ``citation_presence``: does the text contain any [Fonte N] references?
        2. ``phantom_citations``: any [Fonte N] where N > len(citation_anchors)?
           These are out-of-range references that would appear as broken links
           in the Fontes: section.

    Repairs:
        Phantom [Fonte N] brackets are removed from the text (the surrounding
        prose is left intact). Valid citations are never modified.

    Args:
        text: Final summary text (after LLM synthesis).
        citation_anchors: The ordered list of chunks used as [Fonte 1]..[Fonte N]
            in the LLM context. Defines the valid citation range.

    Returns:
        Tuple of ``(validated_text, validation_info)``.

        ``validation_info`` keys:
            - ``citations_found`` (int): total [Fonte N] references in text.
            - ``max_valid_index`` (int): highest valid index (= len(citation_anchors)).
            - ``phantom_indices`` (list[int]): out-of-range indices that were removed.
            - ``repaired`` (bool): True if any phantom was removed.
            - ``no_citations`` (bool): True if the text had zero inline citations.
    """
    max_valid = len(citation_anchors)

    # Collect all [Fonte N] references in the text
    all_indices = [int(m) for m in _CITATION_RE.findall(text)]
    citations_found = len(all_indices)
    phantom_indices = sorted(set(n for n in all_indices if n > max_valid))

    repaired = False
    if phantom_indices:
        def _remove_phantom(match: re.Match) -> str:
            return "" if int(match.group(1)) > max_valid else match.group(0)

        text = _CITATION_RE.sub(_remove_phantom, text)
        repaired = True
        logger.warning(
            "Deep summary citation validation: removed %d phantom index(es) "
            "(valid range 1..%d, found out-of-range: %s).",
            len(phantom_indices),
            max_valid,
            phantom_indices,
        )

    no_citations = citations_found == 0
    if no_citations:
        logger.warning(
            "Deep summary has no inline [Fonte N] citations — "
            "sources section will be appended without inline references."
        )

    return text, {
        "citations_found": citations_found,
        "max_valid_index": max_valid,
        "phantom_indices": phantom_indices,
        "repaired": repaired,
        "no_citations": no_citations,
    }


def _strip_sources_section(text: str) -> str:
    """Remove any model-generated sources section before appending the authoritative one."""
    if not text:
        return text
    return _SOURCES_SECTION_RE.sub("", text).rstrip()


def _sanitize_inline_source_noise(text: str) -> str:
    """Remove source-list artifacts that leak into the summary body."""
    if not text:
        return text

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _INLINE_SOURCES_LINE_RE.match(stripped):
            continue
        if _SOURCE_MAPPING_LINE_RE.match(stripped):
            continue
        if _SOURCE_BULLET_LINE_RE.match(stripped):
            continue
        if _ORPHAN_CITATION_LINE_RE.match(stripped):
            continue
        if _SOURCE_LABEL_LINE_RE.match(stripped):
            continue
        if _looks_like_orphan_source_label(stripped):
            continue
        if _REPAIR_META_LINE_RE.match(stripped):
            continue
        # Source dump inline: line starts with [Fonte N] and is a listing, not prose.
        if _SOURCE_DUMP_MULTI_RE.match(stripped):
            continue
        if _SOURCE_DUMP_ENTRY_RE.match(stripped):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _has_forbidden_repair_patterns(text: str) -> bool:
    """Return True when text contains source/meta artifacts that invalidate repair.

    This checks for *structural* source-dump patterns (Fontes: sections, mapping
    lines, orphan citation lines, meta-commentary).  It does NOT flag legitimate
    inline ``[Fonte N]`` citations embedded in prose or bullet-list explanations,
    which are normal and expected in repaired blocks.
    """
    if not text:
        return False
    if _SOURCES_SECTION_RE.search(text):
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # "Fontes:" or "**Fontes:**" standalone header
        if _INLINE_SOURCES_LINE_RE.match(stripped):
            return True
        # "[Fonte N]: description" mapping lines
        if _SOURCE_MAPPING_LINE_RE.match(stripped):
            return True
        # Lines that are ONLY citation markers with no prose
        if _ORPHAN_CITATION_LINE_RE.match(stripped):
            return True
        # "Fonte N" or "Fonte N: ..." bare label lines
        if _SOURCE_LABEL_LINE_RE.match(stripped):
            return True
        if _looks_like_orphan_source_label(stripped):
            return True
        # Meta-commentary about repair process
        if _REPAIR_META_LINE_RE.match(stripped):
            return True
        # Source dump: line starts with [Fonte N] followed by more [Fonte N]
        if _SOURCE_DUMP_MULTI_RE.match(stripped):
            return True
        # Source dump: [Fonte N] followed by file metadata (page/pdf)
        if _SOURCE_DUMP_ENTRY_RE.match(stripped):
            return True
        # NOTE: _SOURCE_BULLET_LINE_RE is intentionally NOT checked here.
        # A line like "- [Fonte 1] texto explicativo..." is a legitimate
        # bullet-list citation in prose, not a source dump.
    return False


def _clean_repair_source_text(text: str) -> str:
    """Normalize source text passed to block-repair prompt."""
    if not text:
        return text
    text = _META_HEADER_RE.sub("", text.strip())
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _looks_like_orphan_source_label(line: str) -> bool:
    """Detect source-label artifacts like 'Fonte 9' with noisy punctuation."""
    if not line:
        return False
    normalized = _normalize_heading_for_match(line)
    return bool(re.match(r"^fonte\s+\d+$", normalized))


def _extract_used_citation_indices(text: str, max_valid: int) -> list[int]:
    """Return sorted unique [Fonte N] indices present in text and within valid range."""
    if not text or max_valid <= 0:
        return []
    used = {
        int(m)
        for m in _CITATION_RE.findall(text)
        if 1 <= int(m) <= max_valid
    }
    return sorted(used)


def _normalize_heading_for_match(text: str) -> str:
    """Normalize heading text for loose keyword matching."""
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


# ── Step 6d: lightweight semantic grounding check ────────────────────────────

def _parse_sections(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse markdown level-2 sections (##) preserving order."""
    matches = list(_SECTION_HEADING_RE.finditer(text or ""))
    # Fallback for drafts that use only "###" headings.
    if not matches:
        matches = list(_SECTION_HEADING_H3_RE.finditer(text or ""))
    if not matches:
        return (text or "").strip(), []

    preamble = (text or "")[: matches[0].start()].strip()
    sections: list[dict[str, Any]] = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = (text or "")[body_start:body_end].strip()
        sections.append({"title": title, "body": body})

    return preamble, sections


def _strip_inline_citations(text: str) -> str:
    """Remove [Fonte N] markers from text."""
    if not text:
        return text
    return _CITATION_RE.sub("", text)


def _is_section_generic_or_weak(body: str, min_section_chars: int) -> bool:
    """Heuristic guardrail for low-signal sections."""
    if not body or not body.strip():
        return True
    if _has_forbidden_repair_patterns(body):
        return True

    plain = _strip_inline_citations(body)
    plain = re.sub(r"[`*_>#\-\[\]\(\)]", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    words = re.findall(r"\w+", plain)
    bullet_lines = re.findall(r"(?m)^\s*(?:[-*]|\d+[\.\)])\s+(.+)$", body or "")
    bullet_words = sum(
        len(re.findall(r"\w+", _strip_inline_citations(item)))
        for item in bullet_lines
    )
    # Reduced thresholds: 80 chars / 8 words avoids flagging paragraphs
    # with dense citation markup as "weak" when they carry real content.
    if len(plain) < min(min_section_chars, 80) or len(words) < 8:
        normalized_plain = _normalize_heading_for_match(plain)
        technical_short_section = bool(
            _COVERAGE_FORMULA_SUMMARY_RE.search(plain)
            or _COVERAGE_PROCEDURE_SUMMARY_RE.search(plain)
            or re.search(
                r"\b(?:entrop|gini|log2|argmin|alpha|beta|gamma|r t|h s|cost complexity)\b",
                normalized_plain,
                re.IGNORECASE,
            )
        )
        list_style_with_substance = len(bullet_lines) >= 3 and bullet_words >= 18
        if not technical_short_section and not list_style_with_substance:
            return True

    normalized = _normalize_heading_for_match(plain)
    generic_prefixes = (
        "o documento explora",
        "o documento aborda",
        "o documento apresenta",
        "o material aborda",
        "o material apresenta",
        "este documento explora",
        "este documento aborda",
    )
    if normalized.startswith(generic_prefixes) and len(words) < 40:
        return True

    return False


def validate_summary_structure(
    text: str,
    min_section_chars: int = 160,
    min_sections: int = 4,
    max_sections: int = 6,
) -> dict[str, Any]:
    """Validate deep-summary structure quality (headings + section density)."""
    preamble, sections = _parse_sections(text)
    section_count = len(sections)
    weak_indices: list[int] = []
    weak_titles: list[str] = []
    closure_section_ok = False
    closure_heading_count = 0

    category_hits_heading: dict[str, bool] = {
        category: False for category in _REQUIRED_SECTION_CATEGORIES
    }
    body_fallback_categories: list[str] = []

    for i, section in enumerate(sections):
        title = section["title"]
        body = section["body"]
        title_norm = _normalize_heading_for_match(title)

        for category, keywords in _REQUIRED_SECTION_CATEGORIES.items():
            if any(keyword in title_norm for keyword in keywords):
                category_hits_heading[category] = True
                if category == "closure":
                    closure_heading_count += 1

        if _is_section_generic_or_weak(body, min_section_chars=min_section_chars):
            weak_indices.append(i)
            weak_titles.append(title)
        elif any(
            keyword in title_norm for keyword in _REQUIRED_SECTION_CATEGORIES.get("closure", ())
        ):
            body_no_citations = _strip_inline_citations(body)
            closure_words = len(re.findall(r"\w+", body_no_citations))
            if closure_words >= 8:
                closure_section_ok = True

    category_hits: dict[str, bool] = dict(category_hits_heading)
    if sections:
        normalized_bodies = [
            _normalize_heading_for_match(section.get("body", ""))
            for section in sections
            if section.get("body")
        ]
        for category in _REQUIRED_SECTION_CATEGORIES:
            if category_hits_heading.get(category):
                continue
            pattern = _SECTION_BODY_FALLBACK_PATTERNS.get(category)
            if pattern and any(pattern.search(body) for body in normalized_bodies):
                category_hits[category] = True
                body_fallback_categories.append(category)

    missing_categories = [
        category for category, hit in category_hits.items() if not hit
    ]
    missing_heading_categories = [
        category for category, hit in category_hits_heading.items() if not hit
    ]

    # Allow up to 1 weak section as long as the remaining count still meets
    # the minimum.  This avoids flagging an otherwise solid summary as invalid
    # just because one section is slightly thin.
    effective_strong = section_count - len(weak_indices)
    valid = (
        section_count >= min_sections
        and section_count <= max_sections
        and not missing_categories
        and effective_strong >= min_sections
        and closure_section_ok
    )

    # Build a structured failure reason for diagnostics
    failure_reasons: list[str] = []
    if section_count < min_sections:
        failure_reasons.append("section_count_below_min")
    if section_count > max_sections:
        failure_reasons.append("section_count_exceeded")
    if missing_categories:
        failure_reasons.append("missing_categories")
    if effective_strong < min_sections:
        failure_reasons.append("weak_sections")
    if not closure_section_ok:
        failure_reasons.append("weak_closure")
    structure_failure_reason = "|".join(failure_reasons) if failure_reasons else ""

    return {
        "valid": valid,
        "preamble_present": bool(preamble),
        "section_count": section_count,
        "min_sections": min_sections,
        "max_sections": max_sections,
        "missing_categories": missing_categories,
        "missing_heading_categories": missing_heading_categories,
        "body_fallback_categories": body_fallback_categories,
        "weak_section_indices": weak_indices,
        "weak_section_titles": weak_titles,
        "closure_heading_count": closure_heading_count,
        "closure_section_ok": closure_section_ok,
        "structure_failure_reason": structure_failure_reason,
    }


def _is_structure_degraded(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Return True when candidate structure is worse than baseline structure.

    Backfill should not be rejected just because the baseline summary is already
    structurally invalid. We only block backfill when it degrades structure.
    """
    before_valid = bool(before.get("valid", False))
    after_valid = bool(after.get("valid", False))

    # Any valid structure is acceptable.
    if after_valid:
        return False
    # Regressed from valid to invalid.
    if before_valid and not after_valid:
        return True

    before_count = int(before.get("section_count", 0) or 0)
    after_count = int(after.get("section_count", 0) or 0)
    before_missing = len(before.get("missing_categories", []) or [])
    after_missing = len(after.get("missing_categories", []) or [])
    before_weak = len(before.get("weak_section_indices", []) or [])
    after_weak = len(after.get("weak_section_indices", []) or [])
    before_closure = bool(before.get("closure_section_ok", False))
    after_closure = bool(after.get("closure_section_ok", False))

    return (
        after_count < before_count
        or after_missing > before_missing
        or after_weak > before_weak
        or (before_closure and not after_closure)
    )


def _drop_weak_sections(text: str, weak_indices: list[int]) -> str:
    """Remove weak sections from a markdown summary body."""
    if not weak_indices:
        return text
    preamble, sections = _parse_sections(text)
    weak_set = set(weak_indices)
    keep = [
        section
        for idx, section in enumerate(sections)
        if idx not in weak_set
    ]
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for section in keep:
        body = section["body"].strip()
        parts.append(
            f"## {section['title']}\n{body}" if body else f"## {section['title']}"
        )
    return "\n\n".join(part for part in parts if part).strip()


# ── Pre-validation sanitization ──────────────────────────────────────────────

# Orphan "Fonte N" or "Fonte N:" lines that sit alone (no surrounding prose).
_ORPHAN_FONTE_LINE_RE = re.compile(
    r"^\s*Fonte\s+\d+\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Orphan formula line: a line that is *only* a LaTeX-style expression or
# short math fragment with no prose context.  We reattach these to the
# previous paragraph instead of dropping them.
_ORPHAN_FORMULA_LINE_RE = re.compile(
    r"^\s*(\$\$?[^$]+\$\$?|\\[a-zA-Z]+\{[^}]*\})\s*$",
    re.MULTILINE,
)


def _sanitize_before_structure_validation(text: str) -> str:
    """Remove orphan source/metadata lines before structure validation.

    Targets:
    - Orphan ``Fonte N`` or ``Fonte N:`` lines (no useful prose).
    - Residual source-dump blocks that leaked into the body.
    - Orphan inline-citation-only lines (already handled by
      ``_sanitize_inline_source_noise`` but reinforced here).
    - Orphan formula lines are reattached to the previous paragraph
      rather than dropped.
    """
    if not text:
        return text

    # Line-oriented filters (same approach as _sanitize_inline_source_noise)
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        # Orphan "Fonte N" / "Fonte N:" lines
        if _ORPHAN_FONTE_LINE_RE.match(stripped):
            continue
        # Orphan citation-only lines
        if _ORPHAN_CITATION_LINE_RE.match(stripped):
            continue
        # Source label lines (e.g. "Fonte 6: Random Forest")
        if _SOURCE_LABEL_LINE_RE.match(stripped):
            continue
        if _looks_like_orphan_source_label(stripped):
            continue
        # Source dump: multiple [Fonte N] on one line
        if _SOURCE_DUMP_MULTI_RE.match(stripped):
            continue
        # Source dump: [Fonte N] with file metadata
        if _SOURCE_DUMP_ENTRY_RE.match(stripped):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Reattach orphan formula lines to previous paragraph
    def _reattach_formula(m: re.Match) -> str:
        return m.group(1).strip()
    text = _ORPHAN_FORMULA_LINE_RE.sub(_reattach_formula, text)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Deterministic auto-merge for excess sections ─────────────────────────────

# Preferred merge pairs: when section_count > max_sections, these pairs of
# heading keywords are merged first (second merges into first).
_MERGE_PAIR_KEYWORDS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    # "Exemplos" + "Aplicações" → merge into whichever comes first
    (("exemplo", "ilustra", "caso"), ("aplica", "varia", "implica")),
    # "Fundamentos" + "Construção Lógica" → merge
    (("fundament", "base", "princip", "teoria"), ("constru", "encadeamento", "fluxo")),
    # "Conceitos" + "Definições" → merge
    (("conceit", "defini", "termin"), ("nocion", "nocao", "nomenclatura")),
    # "Síntese" + "Conclusão" → merge
    (("sinte", "resumo final"), ("conclus", "fechamento", "considerac")),
]


def _heading_matches_keywords(title_norm: str, keywords: tuple[str, ...]) -> bool:
    """Check whether a normalized heading matches any keyword."""
    return any(kw in title_norm for kw in keywords)


def _auto_merge_sections(text: str, target_sections: int = 5) -> tuple[str, dict[str, Any]]:
    """Deterministically merge sections to reach exactly ``target_sections``.

    Strategy:
    1. Parse current sections.
    2. If section_count <= target_sections, return unchanged.
    3. Try preferred merge pairs first (merge second into first by appending body).
    4. If still above target, merge the two shortest adjacent sections.
    5. Repeat until target is reached.

    Preserves the 4 required categories whenever possible.

    Returns:
        ``(merged_text, merge_info)`` where ``merge_info`` has:
            ``section_count_before``, ``section_count_after``,
            ``merges_applied`` (list of merge descriptions).
    """
    preamble, sections = _parse_sections(text)
    section_count_before = len(sections)

    if section_count_before <= target_sections:
        return text, {
            "section_count_before": section_count_before,
            "section_count_after": section_count_before,
            "merges_applied": [],
        }

    merges_applied: list[str] = []

    # Normalize all titles for keyword matching
    norm_titles = [_normalize_heading_for_match(s["title"]) for s in sections]

    # Phase 1: preferred merge pairs
    while len(sections) > target_sections:
        merged_one = False
        for kw_a, kw_b in _MERGE_PAIR_KEYWORDS:
            if len(sections) <= target_sections:
                break
            # Find indices matching each side
            idx_a = [i for i, t in enumerate(norm_titles) if _heading_matches_keywords(t, kw_a)]
            idx_b = [i for i, t in enumerate(norm_titles) if _heading_matches_keywords(t, kw_b)]
            if not idx_a or not idx_b:
                continue
            # Pick the first pair where they are distinct
            for ia in idx_a:
                for ib in idx_b:
                    if ia == ib:
                        continue
                    # Merge ib into ia (keep ia's title, append ib's body)
                    keep_idx = min(ia, ib)
                    drop_idx = max(ia, ib)
                    merged_title = sections[keep_idx]["title"]
                    merged_body = (
                        sections[keep_idx]["body"].rstrip()
                        + "\n\n"
                        + sections[drop_idx]["body"].strip()
                    )
                    merges_applied.append(
                        f"merged '{sections[drop_idx]['title']}' into '{sections[keep_idx]['title']}'"
                    )
                    sections[keep_idx] = {"title": merged_title, "body": merged_body}
                    sections.pop(drop_idx)
                    norm_titles.pop(drop_idx)
                    merged_one = True
                    break
                if merged_one:
                    break
            if merged_one:
                break
        if not merged_one:
            break

    # Phase 2: merge shortest adjacent pairs
    while len(sections) > target_sections:
        # Find pair of adjacent sections with smallest combined body length
        min_combined = float("inf")
        merge_idx = 0
        for i in range(len(sections) - 1):
            combined = len(sections[i]["body"]) + len(sections[i + 1]["body"])
            if combined < min_combined:
                min_combined = combined
                merge_idx = i

        merged_title = sections[merge_idx]["title"]
        merged_body = (
            sections[merge_idx]["body"].rstrip()
            + "\n\n"
            + sections[merge_idx + 1]["body"].strip()
        )
        merges_applied.append(
            f"merged '{sections[merge_idx + 1]['title']}' into '{sections[merge_idx]['title']}' (shortest pair)"
        )
        sections[merge_idx] = {"title": merged_title, "body": merged_body}
        sections.pop(merge_idx + 1)
        norm_titles.pop(merge_idx + 1)

    # Rebuild text
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for section in sections:
        body = section["body"].strip()
        parts.append(
            f"## {section['title']}\n{body}" if body else f"## {section['title']}"
        )
    merged_text = "\n\n".join(part for part in parts if part).strip()

    return merged_text, {
        "section_count_before": section_count_before,
        "section_count_after": len(sections),
        "merges_applied": merges_applied,
    }


def detect_coverage_signals(chunks: list[Document]) -> dict[str, Any]:
    """Detect content signal types present in document chunks.

    Scans cleaned chunk texts for four heuristic signal types:
    - ``formula``: mathematical notation, Greek letters, algebraic patterns.
    - ``procedure``: step/algorithm markers, procedural vocabulary.
    - ``example``: explicit example markers and illustrative phrases.
    - ``concept``: bold-term definitions and definitional phrases.

    A signal type is marked as *present* when at least one chunk matches its
    pattern. The chunk counts are returned for observability.

    Args:
        chunks: Cleaned document chunks (``Document`` objects with
            ``page_content``).

    Returns:
        Dict with keys:
            ``formula_chunks``   — number of chunks with math/formula content.
            ``procedure_chunks`` — number of chunks with procedural content.
            ``example_chunks``   — number of chunks with example content.
            ``concept_chunks``   — number of chunks with concept/definition patterns.
            ``total_chunks``     — total number of chunks scanned.
            ``has_formulas``     — True if formula_chunks >= 1.
            ``has_procedures``   — True if procedure_chunks >= 1.
            ``has_examples``     — True if example_chunks >= 1.
            ``has_concepts``     — True if concept_chunks >= 1.
    """
    formula_chunks = 0
    procedure_chunks = 0
    example_chunks = 0
    concept_chunks = 0

    for chunk in chunks:
        text = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
        if not text:
            continue
        if _COVERAGE_FORMULA_SIGNAL_RE.search(text):
            formula_chunks += 1
        if _COVERAGE_PROCEDURE_SIGNAL_RE.search(text):
            procedure_chunks += 1
        if _COVERAGE_EXAMPLE_SIGNAL_RE.search(text):
            example_chunks += 1
        if _COVERAGE_CONCEPT_SIGNAL_RE.search(text):
            concept_chunks += 1

    return {
        "formula_chunks": formula_chunks,
        "procedure_chunks": procedure_chunks,
        "example_chunks": example_chunks,
        "concept_chunks": concept_chunks,
        "total_chunks": len(chunks),
        "has_formulas": formula_chunks >= 1,
        "has_procedures": procedure_chunks >= 1,
        "has_examples": example_chunks >= 1,
        "has_concepts": concept_chunks >= 1,
    }


def score_coverage(
    final_text: str,
    signals: dict[str, Any],
    coverage_profile: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Measure how well the summary covers the document's detected content signals.

    Each signal type that is *present* in the source chunks contributes a
    coverage sub-score in [0, 1].  Absent signal types contribute 1.0 (no
    penalty — we cannot fault the summary for omitting content that was never
    in the source).

    The overall score is a weighted mean over *active* (present) signal types.
    If no signals are detected, returns 1.0 (nothing to cover).

    Weights are read from config (``summary_coverage_weight_*``) and default to:
    formula=0.30, procedure=0.30, example=0.20, concept=0.20.

    The concept signal requires at least ``summary_coverage_concept_min_hits``
    (default: 2) chunks with concept patterns before it contributes to the score;
    this avoids penalising summaries of documents with only incidental definitions.

    Args:
        final_text: The final summary text (before the Fontes: section is appended).
        signals:    Output of :func:`detect_coverage_signals`.
        coverage_profile: Optional resolved coverage profile dict. When provided,
            its weights and concept_min_hits are used instead of global config.

    Returns:
        Dict with keys:
            ``formula_coverage``   — float in [0, 1].
            ``procedure_coverage`` — float in [0, 1].
            ``example_coverage``   — float in [0, 1].
            ``concept_coverage``   — float in [0, 1].
            ``overall_coverage_score`` — weighted mean over active types, float in [0, 1].
    """
    if not signals or not final_text:
        return {
            "formula_coverage": 1.0,
            "procedure_coverage": 1.0,
            "example_coverage": 1.0,
            "concept_coverage": 1.0,
            "overall_coverage_score": 1.0,
        }

    if coverage_profile is not None:
        weights: dict[str, float] = {
            "formula": float(coverage_profile.get("weight_formula", 0.30)),
            "procedure": float(coverage_profile.get("weight_procedure", 0.30)),
            "example": float(coverage_profile.get("weight_example", 0.20)),
            "concept": float(coverage_profile.get("weight_concept", 0.20)),
        }
        concept_min_hits = int(coverage_profile.get("concept_min_hits", 2))
    else:
        weights = {
            "formula":   float(getattr(config, "summary_coverage_weight_formula",   0.30)),
            "procedure": float(getattr(config, "summary_coverage_weight_procedure", 0.30)),
            "example":   float(getattr(config, "summary_coverage_weight_example",   0.20)),
            "concept":   float(getattr(config, "summary_coverage_weight_concept",   0.20)),
        }
        concept_min_hits = int(getattr(config, "summary_coverage_concept_min_hits", 2))

    # ── Per-type coverage ─────────────────────────────────────────────────────

    # Formula: 2 keyword/symbol hits in summary = full coverage.
    if signals.get("has_formulas"):
        hits = len(_COVERAGE_FORMULA_SUMMARY_RE.findall(final_text))
        formula_cov = min(1.0, hits / 2)
    else:
        formula_cov = 1.0

    # Procedure: 2 procedural-keyword hits in summary = full coverage.
    if signals.get("has_procedures"):
        hits = len(_COVERAGE_PROCEDURE_SUMMARY_RE.findall(final_text))
        procedure_cov = min(1.0, hits / 2)
    else:
        procedure_cov = 1.0

    # Example: 1 example keyword hit in summary = full coverage.
    if signals.get("has_examples"):
        hits = len(_COVERAGE_EXAMPLE_SUMMARY_RE.findall(final_text))
        example_cov = min(1.0, hits / 1)
    else:
        example_cov = 1.0

    # Concept: only active when concept_chunks >= concept_min_hits.
    # 2 definitional-keyword hits in summary = full coverage.
    concept_active = (
        signals.get("has_concepts", False)
        and signals.get("concept_chunks", 0) >= concept_min_hits
    )
    if concept_active:
        hits = len(_COVERAGE_CONCEPT_SUMMARY_RE.findall(final_text))
        concept_cov = min(1.0, hits / 2)
    else:
        concept_cov = 1.0

    # ── Weighted overall ─────────────────────────────────────────────────────
    active: list[tuple[float, float]] = []
    if signals.get("has_formulas"):
        active.append((formula_cov, weights["formula"]))
    if signals.get("has_procedures"):
        active.append((procedure_cov, weights["procedure"]))
    if signals.get("has_examples"):
        active.append((example_cov, weights["example"]))
    if concept_active:
        active.append((concept_cov, weights["concept"]))

    if not active:
        overall = 1.0
    else:
        total_w = sum(w for _, w in active)
        overall = sum(cov * w for cov, w in active) / total_w if total_w > 0 else 1.0

    return {
        "formula_coverage":   formula_cov,
        "procedure_coverage": procedure_cov,
        "example_coverage":   example_cov,
        "concept_coverage":   concept_cov,
        "overall_coverage_score": round(overall, 4),
    }


def _compute_weak_ratio(grounding_info: dict[str, Any]) -> float:
    """Return weakly-grounded ratio in [0, 1]."""
    cited_blocks = int(grounding_info.get("blocks_with_citations", 0))
    weak_blocks = int(grounding_info.get("weakly_grounded", 0))
    if cited_blocks <= 0:
        return 0.0
    return weak_blocks / cited_blocks


def _resolve_grounding_threshold(
    raw_chunks: list[Document],
    cleaned_chunks: list[Document],
    base_threshold: float,
) -> float:
    """Adapt grounding threshold for noisy extraction artifacts."""
    if not raw_chunks or not cleaned_chunks:
        return base_threshold

    noisy_chunk_ratio_threshold = float(
        getattr(config, "summary_grounding_noisy_chunk_ratio", 0.25)
    )
    noisy_reduction_trigger = float(
        getattr(config, "summary_grounding_noisy_reduction_ratio", 0.03)
    )
    noisy_threshold = float(
        getattr(config, "summary_grounding_threshold_noisy", 0.12)
    )

    total = min(len(raw_chunks), len(cleaned_chunks))
    if total <= 0:
        return base_threshold

    noisy_chunks = 0
    for raw_doc, clean_doc in zip(raw_chunks[:total], cleaned_chunks[:total]):
        raw_text = raw_doc.page_content or ""
        clean_text = clean_doc.page_content or ""
        if not raw_text:
            continue

        reduction = max(0, len(raw_text) - len(clean_text)) / max(len(raw_text), 1)
        symbol_ratio = len(
            re.findall(r"[^\w\s\.,;:!?()\[\]\-+/=*<>%]", raw_text)
        ) / max(len(raw_text), 1)
        has_artifact_glyph = bool(_ARTIFACT_CHAR_RE.search(raw_text))

        if (
            has_artifact_glyph
            or reduction >= noisy_reduction_trigger
            or symbol_ratio >= 0.22
        ):
            noisy_chunks += 1

    noisy_ratio = noisy_chunks / total
    if noisy_ratio >= noisy_chunk_ratio_threshold:
        adapted = min(base_threshold, noisy_threshold)
        logger.info(
            "Deep summary grounding threshold adapted for noisy extraction: %.2f -> %.2f "
            "(noisy_chunks=%d/%d, ratio=%.2f, trigger=%.2f).",
            base_threshold,
            adapted,
            noisy_chunks,
            total,
            noisy_ratio,
            noisy_chunk_ratio_threshold,
        )
        return adapted
    return base_threshold


def _quality_signature(
    structure_info: dict[str, Any],
    grounding_info: dict[str, Any],
    unique_sources: int,
    min_unique_sources: int,
) -> tuple:
    """Lexicographic quality signature used to compare two candidate summaries."""
    weak_ratio = _compute_weak_ratio(grounding_info)
    return (
        int(bool(structure_info.get("valid"))),
        int(unique_sources >= min_unique_sources),
        -round(weak_ratio, 4),
        unique_sources,
        -len(structure_info.get("weak_section_indices", [])),
    )


def _postprocess_deep_summary_text(
    text: str,
    citation_anchors: list[Document],
    grounding_threshold: float,
    llm,
    repair_enabled: bool,
    structure_min_chars: int,
) -> tuple[str, dict[str, Any]]:
    """Normalize, validate, and score a deep-summary draft/candidate."""
    text = _strip_sources_section(text)
    text = _sanitize_inline_source_noise(text)

    text, citation_validation = validate_summary_citations(text, citation_anchors)
    text, grounding_info = validate_summary_grounding(
        text,
        citation_anchors,
        threshold=grounding_threshold,
        llm=llm if repair_enabled else None,
    )

    text, post_grounding_validation = validate_summary_citations(text, citation_anchors)
    if post_grounding_validation["repaired"]:
        logger.warning(
            "Deep summary post-grounding citation cleanup: removed %d phantom citation(s).",
            len(post_grounding_validation["phantom_indices"]),
        )

    text = _sanitize_inline_source_noise(text)
    text = clean_summary_output(text)
    text = _strip_sources_section(text)
    text = _sanitize_inline_source_noise(text)

    # Pre-validation sanitization: remove orphan Fonte lines, source dumps,
    # and reattach orphan formulas before structure validation.
    text = _sanitize_before_structure_validation(text)

    structure_info = validate_summary_structure(
        text,
        min_section_chars=structure_min_chars,
    )

    # Auto-merge excess sections deterministically
    auto_merge_applied = False
    merge_info: dict[str, Any] = {}
    if (
        not structure_info.get("valid")
        and structure_info.get("section_count", 0) > structure_info.get("max_sections", 6)
        and "section_count_exceeded" in structure_info.get("structure_failure_reason", "")
    ):
        text, merge_info = _auto_merge_sections(text, target_sections=5)
        auto_merge_applied = bool(merge_info.get("merges_applied"))
        if auto_merge_applied:
            logger.info(
                "Deep summary auto-merge: %d → %d sections (%s).",
                merge_info["section_count_before"],
                merge_info["section_count_after"],
                "; ".join(merge_info["merges_applied"]),
            )
            # Re-validate after merge
            text = _sanitize_inline_source_noise(text)
            text, _ = validate_summary_citations(text, citation_anchors)
            structure_info = validate_summary_structure(
                text,
                min_section_chars=structure_min_chars,
            )

    dropped_weak_sections = 0
    if structure_info["weak_section_indices"]:
        remaining_sections = (
            int(structure_info["section_count"])
            - len(set(structure_info["weak_section_indices"]))
        )
        min_sections_required = int(structure_info.get("min_sections", 4))
        if remaining_sections >= min_sections_required:
            dropped_weak_sections = len(structure_info["weak_section_indices"])
            text = _drop_weak_sections(text, structure_info["weak_section_indices"])
            text = _sanitize_inline_source_noise(text)
            text, _ = validate_summary_citations(text, citation_anchors)
            text = _sanitize_inline_source_noise(text)
            structure_info = validate_summary_structure(
                text,
                min_section_chars=structure_min_chars,
            )

    used_source_indices = _extract_used_citation_indices(text, len(citation_anchors))
    return text, {
        "citation_validation": citation_validation,
        "post_grounding_validation": post_grounding_validation,
        "grounding_info": grounding_info,
        "structure_info": structure_info,
        "used_source_indices": used_source_indices,
        "dropped_weak_sections": dropped_weak_sections,
        "auto_merge_applied": auto_merge_applied,
        "merge_info": merge_info,
    }


def _split_summary_blocks(text: str) -> list[str]:
    """Split a summary into logical blocks at paragraph/section boundaries."""
    blocks = re.split(r"\n{2,}", text)
    return [b.strip() for b in blocks if b.strip()]


def _normalize_token(word: str) -> str:
    """Normalize a token for grounding comparison: lowercase + strip accents."""
    word = word.lower()
    # Strip combining diacritical marks (accents) so "conclusão" == "conclusao"
    decomposed = unicodedata.normalize("NFKD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokenize_for_overlap(text: str, min_len: int = 3) -> set[str]:
    """Extract normalized token set from text for grounding comparison.

    Strips markdown formatting, citation markers, and punctuation before
    tokenizing. Normalizes accents and case so paraphrased text matches
    better (e.g., "conclusão" ↔ "conclusao", "Índice" ↔ "indice").
    """
    if not text:
        return set()
    # Remove markdown formatting and citation markers
    cleaned = re.sub(r"\[Fonte\s*\d+\]", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[#*_`\[\]>|(){}\-]", " ", cleaned)
    # Remove punctuation that glues to words
    cleaned = re.sub(r"[,;:!?\"'""''…·•]", " ", cleaned)
    tokens = set()
    for w in re.findall(r"\w+", cleaned):
        if len(w) >= min_len:
            tokens.add(_normalize_token(w))
    return tokens


def _token_overlap(text_a: str, text_b: str, min_len: int = 3) -> float:
    """Fraction of significant tokens from *text_a* found in *text_b*.

    Uses accent-normalized, case-folded tokens for comparison, making
    the overlap robust to paraphrasing (accent variation, casing, markdown).
    Tokens shorter than ``min_len`` are excluded (mostly stop words in PT/EN).
    Returns 1.0 for empty input (trivially supported).
    """
    tokens_a = _tokenize_for_overlap(text_a, min_len)
    if not tokens_a:
        return 1.0
    tokens_b = _tokenize_for_overlap(text_b, min_len)
    return len(tokens_a & tokens_b) / len(tokens_a)


def _repair_block(
    block: str,
    anchor_texts: list[str],
    indices: list[int],
    llm,
) -> str:
    """Attempt a restricted LLM rewrite of a weakly grounded block."""
    sources_block = "\n\n".join(
        f"[Fonte {n}]: {_clean_repair_source_text(text)[:600]}"
        for n, text in zip(indices, anchor_texts)
    )
    prompt = SUMMARY_BLOCK_REPAIR_PROMPT.format(
        block=block,
        sources_block=sources_block,
    )
    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        repaired_raw = response_text(response)
        # Sanitize first: strip sources section and source-dump noise.
        # This gives the repair a chance even if the LLM leaked a Fontes:
        # block or source-mapping lines alongside valid content.
        repaired = _strip_sources_section(repaired_raw)
        repaired = _sanitize_inline_source_noise(repaired)
        # Only reject if forbidden patterns survive after sanitation.
        if _has_forbidden_repair_patterns(repaired):
            logger.warning(
                "Deep summary block repair rejected: forbidden source/meta pattern "
                "detected after sanitation."
            )
            return block
        return repaired or block
    except Exception as exc:
        logger.warning("Deep summary block repair failed: %s", exc)
        return block  # return original on failure


def validate_summary_grounding(
    text: str,
    citation_anchors: list[Document],
    threshold: float = 0.20,
    llm=None,
) -> tuple[str, dict]:
    """Lightweight semantic grounding check for the final deep summary.

    Splits the summary into paragraph blocks and, for each block that contains
    [Fonte N] citations, measures token overlap between the block text and the
    cited anchor texts. Blocks below ``threshold`` are considered weakly grounded.

    The check is intentionally lenient (default threshold=0.20) because summary
    text paraphrases the source. The goal is detecting blocks that are completely
    disconnected from their cited anchors — not enforcing verbatim fidelity.

    If ``llm`` is provided (and ``SUMMARY_GROUNDING_REPAIR=true``), weakly grounded
    blocks receive a restricted repair pass. Otherwise the function logs warnings
    and returns the text unchanged.

    Args:
        text: Final summary text (after citation validation).
        citation_anchors: Ordered anchor chunks ([Fonte 1]..[Fonte N]).
        threshold: Minimum token overlap to consider a block grounded (default 0.20).
        llm: Optional LLM instance for repair (None = log-only mode).

    Returns:
        ``(text, grounding_info)`` where ``grounding_info`` keys:
            - ``total_blocks`` (int)
            - ``blocks_with_citations`` (int)
            - ``weakly_grounded`` (int): blocks below threshold
            - ``repaired_blocks`` (int): blocks that received LLM repair
            - ``block_scores`` (list[dict]): per-block detail with
              ``block``, ``cited_indices``, ``score``, ``grounded``
    """
    blocks = _split_summary_blocks(text)
    if not blocks:
        return text, {
            "total_blocks": 0,
            "blocks_with_citations": 0,
            "weakly_grounded": 0,
            "repaired_blocks": 0,
            "block_scores": [],
        }

    total_blocks = len(blocks)
    blocks_with_citations = 0
    weakly_grounded_count = 0
    repaired_count = 0
    block_scores: list[dict] = []
    result_blocks = list(blocks)  # mutable copy for in-place repair
    max_repairs_per_pass = max(
        0,
        int(getattr(config, "summary_grounding_max_repairs_per_pass", 1)),
    )
    repair_min_overlap = max(
        0.0,
        min(
            threshold,
            float(getattr(config, "summary_grounding_repair_min_overlap", 0.15)),
        ),
    )
    repair_budget_exhausted = False

    for i, block in enumerate(blocks):
        # Only consider indices that passed citation validation (≤ max_valid)
        raw_indices = [
            int(m)
            for m in _CITATION_RE.findall(block)
            if 1 <= int(m) <= len(citation_anchors)
        ]
        valid_indices = list(dict.fromkeys(raw_indices))
        if not valid_indices:
            block_scores.append(
                {"block": i, "cited_indices": [], "score": None, "grounded": None}
            )
            continue

        blocks_with_citations += 1
        anchor_texts = [citation_anchors[n - 1].page_content for n in valid_indices]
        score = _token_overlap(block, " ".join(anchor_texts))
        grounded = score >= threshold

        block_scores.append(
            {
                "block": i,
                "cited_indices": valid_indices,
                "score": round(score, 3),
                "grounded": grounded,
            }
        )

        if not grounded:
            weakly_grounded_count += 1
            logger.warning(
                "Deep summary grounding: block %d/%d weakly grounded "
                "(overlap=%.2f < threshold=%.2f, cited=[%s]).",
                i + 1,
                total_blocks,
                score,
                threshold,
                ", ".join(f"Fonte {n}" for n in valid_indices),
            )
            if llm is not None:
                if repaired_count >= max_repairs_per_pass:
                    if not repair_budget_exhausted:
                        logger.info(
                            "Deep summary grounding: repair budget exhausted "
                            "(max_repairs_per_pass=%d). Remaining weak blocks will be logged only.",
                            max_repairs_per_pass,
                        )
                        repair_budget_exhausted = True
                    continue
                if score >= repair_min_overlap:
                    logger.info(
                        "Deep summary grounding: block %d repair skipped "
                        "(near-threshold overlap=%.2f >= min_repair_overlap=%.2f).",
                        i + 1,
                        score,
                        repair_min_overlap,
                    )
                    continue
                if score <= 0.0:
                    logger.info(
                        "Deep summary grounding: block %d repair skipped (overlap=0.00).",
                        i + 1,
                    )
                    continue
                if len(valid_indices) > MAX_REPAIR_CITATIONS_PER_BLOCK:
                    logger.info(
                        "Deep summary grounding: block %d repair skipped (cited=%d > max=%d).",
                        i + 1,
                        len(valid_indices),
                        MAX_REPAIR_CITATIONS_PER_BLOCK,
                    )
                    continue
                repaired = _repair_block(block, anchor_texts, valid_indices, llm)
                if repaired and repaired != block:
                    result_blocks[i] = repaired
                    repaired_count += 1
                    logger.info(
                        "Deep summary grounding: block %d repaired.", i + 1
                    )

    if weakly_grounded_count > 0:
        logger.warning(
            "Deep summary grounding: %d/%d cited block(s) weakly grounded, "
            "%d repaired (threshold=%.2f).",
            weakly_grounded_count,
            blocks_with_citations,
            repaired_count,
            threshold,
        )
    elif blocks_with_citations > 0:
        logger.info(
            "Deep summary grounding: all %d cited block(s) passed (threshold=%.2f).",
            blocks_with_citations,
            threshold,
        )

    return "\n\n".join(result_blocks), {
        "total_blocks": total_blocks,
        "blocks_with_citations": blocks_with_citations,
        "weakly_grounded": weakly_grounded_count,
        "repaired_blocks": repaired_count,
        "block_scores": block_scores,
    }


# ── Claim-risk + inference-density fidelity layer ────────────────────────────
#
# These functions run on the final summary text to detect high-risk claims that
# lack proper source support. The results feed the inference_density metric and
# the de-overreach rewrite trigger.

# Low-information source section labels (normalised to lower-case).
# Chunks whose section_title or section_path matches these are "low-info" anchors
# for the purpose of high-risk claim support verification.
_LOW_INFO_SECTION_LABELS: frozenset[str] = frozenset({
    "sumário", "sumario", "índice", "indice", "conteúdo", "conteudo",
    "contents", "table of contents", "lista de figuras", "lista de tabelas",
    "lista de abreviaturas", "lista de siglas", "prefácio", "prefacio",
    "apresentação", "apresentacao", "agradecimentos",
})

# Regex patterns for sentence-level risk classification.
# These complement the existing coverage-signal patterns but operate at
# sentence level to detect over-reach (not just presence of signal).
_RISK_QUANTITATIVE_RE = re.compile(
    # Percentage: "30%", "95,5%" — note: % is non-word char, so no trailing \b
    r"\b\d+(?:[,.]\d+)?\s*%"
    # Verbal percentage: "30 por cento"
    r"|\b\d+\s+por\s+cento\b"
    # Comparison words followed by "que/do que"
    r"|\b(?:maior|menor|superior|inferior|melhor|pior)\s+(?:que|do que|em)\b"
    # Numeric multiplier: "3 vezes maior", "2x mais rápido"
    r"|\b(?:\d+[,.]?\d*)\s*(?:vezes|x)\s+(?:mais|menos|maior|menor)\b"
    # Range: "30 a 50%", "10-20 vezes"
    r"|\b\d+\s*(?:a|até|–|-)\s*\d+\s*(?:vezes?\b|%)",
    re.IGNORECASE,
)

_RISK_COMPARISON_RE = re.compile(
    r"\b(?:em\s+compara[çc][aã]o\s+(?:a|com)|ao\s+contr[aá]rio\s+de"
    r"|diferencia-se\s+de|se\s+difere\s+de|em\s+contraste\s+com"
    r"|enquanto\s+(?:que\s+)?[A-ZÀ-Ú]|\bvs\.?\s+[A-ZÀ-Ú]"
    r"|\bcomparado\s+(?:a|com)\b|\bcontrasta\s+com\b"
    r"|\b[eé]\s+classificado\s+como\b|\bpertence\s+[aà]\s+classe\b"
    r"|\btaxonomia\b|\bcategoriza[çc][aã]o\b"
    r"|\bclassifica[çc][aã]o\s+de\b)\b",
    re.IGNORECASE,
)

# Technical-assertion pattern: claims that infer performance/generalization effects
# (e.g., "mitiga variância", "aumenta robustez") are high-risk when supported only
# by low-information sections (sumário/índice/conteúdo).
_RISK_TECHNICAL_ASSERTION_RE = re.compile(
    r"\b(?:random\s*forest|randomforestregressor|modelo|m[eé]todo|abordagem)\b"
    r".{0,80}\b(?:mitig\w+|reduz\w+|melhor\w+|aument\w+|garant\w+|assegur\w+|"
    r"consolid\w+|otimiz\w+|valida\w+|estabiliz\w+|control\w+)\b"
    r".{0,80}\b(?:vari[aâ]nci\w*|overfitting|sobreajust\w*|generaliza\w*|"
    r"capacidade\s+preditiv\w*|robust\w*|estabilid\w*|desempenh\w*|"
    r"hiperpar[aâ]metr\w*|valida[cç][aã]o)\b"
    r"|"
    r"\b(?:integra|incorpora|utiliza)\b.{0,40}\bprocessos?\s+de\s+valida[cç][aã]o\b",
    re.IGNORECASE | re.DOTALL,
)


def _is_low_info_source(anchor: "Document") -> bool:
    """Return True if the anchor chunk comes from a low-information section.

    Low-info sections (e.g. table of contents, index, prefácio) may contain
    references to other sections but lack the substantive evidence needed to
    support high-risk technical claims.
    """
    meta = anchor.metadata
    section_title = str(meta.get("section_title") or "").strip().lower()
    section_path = str(meta.get("section_path") or "").strip().lower()

    # Check exact match first, then "starts with" for compound paths.
    for label in _LOW_INFO_SECTION_LABELS:
        if section_title == label or section_path == label:
            return True
        # e.g. section_path = "sumário > capítulo 1"
        if section_title.startswith(label) or section_path.startswith(label):
            return True
    return False


def classify_claim_risks(
    text: str,
    citation_anchors: list["Document"],
) -> dict[str, Any]:
    """Classify sentences in the summary by risk level and check source support.

    High-risk claim types (taxonomy/comparison, quantitative, formula,
    procedural, technical-assertion) require
    direct evidence from the cited anchors. If all cited anchors for a high-risk
    sentence come from low-information sources (or none are cited), the claim is
    flagged as unsupported.

    Args:
        text: Final summary text (body only, no Fontes: section).
        citation_anchors: Ordered list of citation anchors used in this summary.
            Index 0 → [Fonte 1], index 1 → [Fonte 2], etc.

    Returns:
        dict with keys:
            sentences_total, sentences_classified, high_risk_count,
            unsupported_high_risk_count, unsupported_high_risk_indices,
            low_info_source_claims_count, low_info_source_claim_indices,
            formula_claims_total, formula_claims_supported,
            formula_claims_downgraded_to_concept (initialised to 0; filled by
            check_formula_mode).
    """
    # Strip sources section if present so we don't analyse citation metadata.
    body = _SOURCES_SECTION_RE.sub("", text).strip()

    # Split body into paragraphs, then sentences.
    paragraphs = re.split(r"\n{1,}", body)
    sentences: list[str] = []
    for para in paragraphs:
        # Skip heading lines and blank lines.
        stripped = para.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Naive sentence split on Portuguese sentence boundaries.
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú\[])", stripped)
        sentences.extend(p.strip() for p in parts if p.strip())

    classified: list[dict[str, Any]] = []
    high_risk_count = 0
    unsupported_high_risk_count = 0
    unsupported_high_risk_indices: list[int] = []
    low_info_source_claims_count = 0
    low_info_source_claim_indices: list[int] = []
    formula_claims_total = 0
    formula_claims_supported = 0

    for idx, sentence in enumerate(sentences):
        # Determine risk type.
        # Use both signal-detection pattern (for raw notation) and the summary-
        # coverage pattern (for natural-language formula references in paraphrased text).
        is_formula = bool(
            _COVERAGE_FORMULA_SIGNAL_RE.search(sentence)
            or _COVERAGE_FORMULA_SUMMARY_RE.search(sentence)
        )
        is_quantitative = bool(_RISK_QUANTITATIVE_RE.search(sentence))
        is_comparison = bool(_RISK_COMPARISON_RE.search(sentence))
        is_procedural = bool(_COVERAGE_PROCEDURE_SIGNAL_RE.search(sentence))
        is_technical_assertion = bool(_RISK_TECHNICAL_ASSERTION_RE.search(sentence))

        if is_formula:
            risk_type = "formula"
        elif is_quantitative:
            risk_type = "quantitative"
        elif is_comparison:
            risk_type = "taxonomy_comparison"
        elif is_technical_assertion:
            risk_type = "technical_assertion"
        elif is_procedural:
            risk_type = "procedural"
        else:
            risk_type = "descriptive"

        high_risk = risk_type in {
            "formula",
            "quantitative",
            "taxonomy_comparison",
            "procedural",
            "technical_assertion",
        }

        if risk_type == "formula":
            formula_claims_total += 1

        # Extract cited anchor indices (1-based from text, convert to 0-based).
        cited_indices_1based = [int(m) for m in _CITATION_RE.findall(sentence)]
        cited_indices_0based = [
            i - 1 for i in cited_indices_1based
            if 1 <= i <= len(citation_anchors)
        ]

        # Check source quality for high-risk claims.
        # The hard rule (require_non_low_info) controls whether low-info-only citations
        # count as "unsupported". When disabled, low-info sources are still flagged in
        # diagnostics but do not increment unsupported_high_risk_count.
        _require_non_low_info = bool(
            getattr(config, "summary_require_non_low_info_for_high_risk", True)
        )
        low_info_only = False
        unsupported = False
        if high_risk:
            high_risk_count += 1
            if not cited_indices_0based:
                # High-risk claim with no citations at all.
                unsupported = True
            else:
                # Check if ALL cited anchors are low-info.
                low_info_anchors = [
                    citation_anchors[i]
                    for i in cited_indices_0based
                    if _is_low_info_source(citation_anchors[i])
                ]
                if len(low_info_anchors) == len(cited_indices_0based):
                    low_info_only = True
                    low_info_source_claims_count += 1
                    low_info_source_claim_indices.append(idx)
                    # Only mark as unsupported when the hard rule is active.
                    if _require_non_low_info:
                        unsupported = True

            if unsupported:
                unsupported_high_risk_count += 1
                unsupported_high_risk_indices.append(idx)
            elif risk_type == "formula":
                formula_claims_supported += 1

        classified.append({
            "text": sentence,
            "risk_type": risk_type,
            "high_risk": high_risk,
            "cited_indices": cited_indices_0based,
            "low_info_only": low_info_only,
            "unsupported": unsupported,
        })

    # unsupported_high_risk_low_info_only_count counts exactly the claims where
    # the *only* reason for being unsupported was low-info sources (not missing citation).
    _unsupported_low_info_only_count = sum(
        1 for c in classified
        if c.get("high_risk") and c.get("low_info_only") and c.get("unsupported")
    )

    return {
        "sentences_total": len(sentences),
        "sentences_classified": classified,
        "high_risk_count": high_risk_count,
        "unsupported_high_risk_count": unsupported_high_risk_count,
        "unsupported_high_risk_indices": unsupported_high_risk_indices,
        "unsupported_high_risk_low_info_only_count": _unsupported_low_info_only_count,
        "low_info_source_claims_count": low_info_source_claims_count,
        "low_info_source_claim_indices": low_info_source_claim_indices,
        "formula_claims_total": formula_claims_total,
        "formula_claims_supported": formula_claims_supported,
        "formula_claims_downgraded_to_concept": 0,  # filled by check_formula_mode
    }


def check_formula_mode(
    claim_risk_result: dict[str, Any],
    citation_anchors: list["Document"],
    formula_mode: str = "conservative",
) -> dict[str, Any]:
    """In conservative mode, verify that formula claims have math-bearing anchors.

    For each sentence classified as 'formula', checks whether at least one of its
    cited anchors contains actual mathematical content (per _COVERAGE_FORMULA_SIGNAL_RE).
    If not, the claim is marked as downgraded_to_concept.

    Args:
        claim_risk_result: Output of classify_claim_risks (mutated copy returned).
        citation_anchors: Same ordered list used in classify_claim_risks.
        formula_mode: 'conservative' (default) or 'permissive'.

    Returns:
        Updated claim_risk_result dict with formula_claims_downgraded_to_concept
        correctly populated.
    """
    if formula_mode != "conservative":
        return claim_risk_result

    result = dict(claim_risk_result)
    classified = list(result.get("sentences_classified", []))
    downgraded = 0

    for entry in classified:
        if entry.get("risk_type") != "formula":
            continue
        cited_indices = entry.get("cited_indices", [])
        if not cited_indices:
            # Already counted as unsupported by classify_claim_risks.
            continue
        # Check if any cited anchor has math content.
        has_math_anchor = any(
            _COVERAGE_FORMULA_SIGNAL_RE.search(citation_anchors[i].page_content or "")
            for i in cited_indices
            if i < len(citation_anchors)
        )
        if not has_math_anchor:
            downgraded += 1
            entry["formula_downgraded"] = True

    result["formula_claims_downgraded_to_concept"] = downgraded
    result["sentences_classified"] = classified
    return result


def compute_inference_density(
    claim_risk_result: dict[str, Any],
) -> dict[str, Any]:
    """Compute the inference-density metric from sentence-level claim-risk results.

    Inference density = fraction of total sentences that are high-risk and either:
    - unsupported (no citation or all-low-info sources), OR
    - formula claims downgraded to concept (conservative mode).

    A density above config.summary_max_inference_density triggers the de-overreach
    rewrite pass and, if unresolved, causes final.accepted=False.

    Returns:
        dict with keys: inference_density, inference_threshold,
                        inference_gate_passed, unsupported_claims_count.
    """
    try:
        threshold = float(getattr(config, "summary_max_inference_density", 0.25))
    except (AttributeError, TypeError, ValueError):
        threshold = 0.25

    unsupported = (
        int(claim_risk_result.get("unsupported_high_risk_count", 0))
        + int(claim_risk_result.get("formula_claims_downgraded_to_concept", 0))
    )
    total = int(claim_risk_result.get("sentences_total", 0))
    density = unsupported / total if total > 0 else 0.0
    gate_passed = density <= threshold

    return {
        "inference_density": round(density, 4),
        "inference_threshold": round(threshold, 4),
        "inference_gate_passed": gate_passed,
        "unsupported_claims_count": unsupported,
    }


def _build_compact_context_block(
    anchors: list["Document"],
    max_sources: int,
    max_chars_per_source: int,
) -> str:
    """Build a reduced context block to keep optional passes fast."""
    if not anchors:
        return "(Nenhum trecho encontrado nos documentos.)"
    keep_sources = max(1, int(max_sources))
    keep_chars = max(120, int(max_chars_per_source))
    compact: list[Document] = []
    for anchor in anchors[:keep_sources]:
        text = (anchor.page_content or "").strip()
        if len(text) > keep_chars:
            cut = text[:keep_chars]
            last_space = cut.rfind(" ")
            if last_space > keep_chars * 0.7:
                cut = cut[:last_space]
            text = cut + "…"
        compact.append(
            Document(
                page_content=text,
                metadata=dict(anchor.metadata or {}),
            )
        )
    return build_context_block(compact)


def run_deoverreach_pass(
    draft: str,
    doc_name: str,
    citation_anchors: list["Document"],
    llm: Any,
) -> str:
    """Run one LLM pass to remove extrapolations from the deep summary draft.

    Triggered when the inference-density gate fails, unsupported high-risk claims
    are detected, or formula claims lack math support in conservative mode.

    The pass preserves: section structure, headings, and valid [Fonte N] citations.
    It removes or reformulates: unsupported quantitative/comparative/mathematical claims.

    Args:
        draft: Current summary text (body only, Fontes: section not included).
        doc_name: Document name for the prompt.
        citation_anchors: Citation anchors (used to build context_sample).
        llm: Chat model instance.

    Returns:
        Rewritten text, or ``draft`` unchanged on LLM failure.
    """
    max_sources = int(getattr(config, "summary_deoverreach_max_context_sources", 6))
    max_chars = int(getattr(config, "summary_deoverreach_context_chars", 700))
    max_prompt_chars = int(getattr(config, "summary_deoverreach_max_prompt_chars", 18000))
    context_sample = _build_compact_context_block(
        citation_anchors,
        max_sources=max_sources,
        max_chars_per_source=max_chars,
    )
    prompt = DEEP_SUMMARY_DEOVERREACH_PROMPT.format(
        doc_name=doc_name,
        draft=draft,
        context_sample=context_sample,
    )
    if len(prompt) > max_prompt_chars:
        logger.info(
            "De-overreach pass skipped: prompt too large (%d chars > limit=%d).",
            len(prompt),
            max_prompt_chars,
        )
        return draft
    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        rewritten = response_text(response)
        if rewritten and rewritten.strip():
            logger.info(
                "De-overreach rewrite pass completed (%d → %d chars).",
                len(draft),
                len(rewritten),
            )
            return rewritten
        logger.warning("De-overreach pass returned empty output; keeping original.")
        return draft
    except Exception as exc:
        logger.warning("De-overreach pass failed (%s); keeping original draft.", exc)
        return draft


# ── Step 6: final polished deep summary ──────────────────────────────────────

def _select_citation_anchors(
    all_chunks: list[Document],
    groups: list[list[Document]],
    max_anchors: int = 12,
    topic_info: dict[str, Any] | None = None,
) -> list[Document]:
    """Select representative chunks to serve as citation anchors for the final synthesis.

    Strategy (in priority order):
    1. One anchor per group — pick the most content-rich chunk, not just the first.
    2. Topic-aware fill: ensure each must-cover topic has at least one anchor.
    3. Late-document coverage: ensure the last third of groups get representation.
    4. Evenly-spaced fill from remaining chunks.

    This ensures every logical section AND every major topic has citable evidence.
    """
    # Phase 1: Best chunk per group (prefer chunk with most content).
    anchors: list[Document] = []
    anchor_ids: set[int] = set()

    for g in groups:
        if not g:
            continue
        # Prefer non-low-info chunks (avoid sumário/índice as primary evidence).
        eligible = [c for c in g if not _is_low_info_source(c)]
        pool = eligible or g
        # Pick the chunk with the most content, not just the first.
        best = max(pool, key=lambda c: len(c.page_content or ""))
        anchors.append(best)
        anchor_ids.add(id(best))

    if len(anchors) >= max_anchors:
        return anchors[:max_anchors]

    # Phase 2: Topic-aware fill — ensure every must-cover topic has an anchor.
    if topic_info:
        topic_anchors_map = get_topic_anchors(topic_info, all_chunks, max_per_topic=2)
        for _topic_id, chunk_indices in topic_anchors_map.items():
            if len(anchors) >= max_anchors:
                break
            preferred_ci = None
            fallback_ci = None
            for ci in chunk_indices:
                if ci >= len(all_chunks):
                    continue
                candidate = all_chunks[ci]
                if id(candidate) in anchor_ids:
                    continue
                if not _is_low_info_source(candidate):
                    preferred_ci = ci
                    break
                if fallback_ci is None:
                    fallback_ci = ci
            chosen_ci = preferred_ci if preferred_ci is not None else fallback_ci
            if chosen_ci is not None:
                chosen = all_chunks[chosen_ci]
                anchors.append(chosen)
                anchor_ids.add(id(chosen))

    if len(anchors) >= max_anchors:
        return anchors[:max_anchors]

    # Phase 3: Late-document coverage — ensure last third of chunks is represented.
    n_chunks = len(all_chunks)
    if n_chunks >= 6:
        late_start = n_chunks * 2 // 3
        late_chunks = [c for c in all_chunks[late_start:] if id(c) not in anchor_ids]
        if late_chunks and len(anchors) < max_anchors:
            # Prefer non-low-info evidence in late coverage.
            late_non_low_info = [c for c in late_chunks if not _is_low_info_source(c)]
            source_late = late_non_low_info or late_chunks
            # Add one from the middle of the late section.
            mid_late = source_late[len(source_late) // 2] if source_late else None
            if mid_late:
                anchors.append(mid_late)
                anchor_ids.add(id(mid_late))

    if len(anchors) >= max_anchors:
        return anchors[:max_anchors]

    # Phase 4: Evenly-spaced fill from remainder.
    remaining = [c for c in all_chunks if id(c) not in anchor_ids]
    # Keep low-info chunks as last resort only.
    remaining.sort(key=lambda c: 1 if _is_low_info_source(c) else 0)
    if remaining:
        slots = max_anchors - len(anchors)
        step = max(1, len(remaining) // max(1, slots))
        extras = remaining[::step][:slots]
        anchors.extend(extras)

    return anchors[:max_anchors]


def finalize_deep_summary(
    consolidated: str,
    partials: list[str],
    doc_name: str,
    citation_anchors: list[Document],
    coverage_contract: str,
    llm,
) -> str:
    """Produce the final structured deep summary using the consolidated + partial views.

    ``citation_anchors`` is the pre-selected list of representative chunks that
    will be numbered [Fonte 1]..[Fonte N] in both the LLM context and the final
    Fontes: section. The caller is responsible for selecting them (via
    ``_select_citation_anchors``) BEFORE calling this function, so the same list
    can be reused for citation validation and the sources section.

    Args:
        consolidated: Output of ``consolidate_summaries``.
        partials: List of partial summary strings (one per group).
        doc_name: Document file name for display and prompt formatting.
        citation_anchors: Ordered chunks used as [Fonte 1]..[Fonte N] in the
            synthesis prompt. These define the valid citation index range.
        llm: LLM instance to call.

    Returns:
        Raw synthesis text (not yet cleaned or validated).
    """
    partials_block = "\n\n".join(partials)
    context_sample = build_context_block(citation_anchors)

    prompt = DEEP_SUMMARY_FINAL_PROMPT.format(
        doc_name=doc_name,
        consolidated=consolidated,
        partials_block=partials_block,
        context_sample=context_sample,
        coverage_contract=coverage_contract,
    )

    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        result = response_text(response)
        logger.debug("Final synthesis done (%d chars).", len(result))
        return result
    except Exception as exc:
        logger.error("Final synthesis failed: %s", exc)
        # Fallback: return the consolidated view with a heading
        return f"# Resumo Aprofundado — {doc_name}\n\n{consolidated}"


# ── Public entry point ────────────────────────────────────────────────────────

def polish_deep_summary_style(
    draft: str,
    doc_name: str,
    llm,
) -> str:
    """Polish the deep-summary draft into a more cohesive study-oriented explanation."""
    prompt = DEEP_SUMMARY_STYLE_POLISH_PROMPT.format(
        doc_name=doc_name,
        draft=draft,
    )

    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        polished = response_text(response)
        logger.debug("Deep summary style polish done (%d chars).", len(polished))
        return polished or draft
    except Exception as exc:
        logger.warning("Deep summary style polish failed: %s", exc)
        return draft


def _run_micro_topic_backfill(
    final_text: str,
    missing_topics: list[str],
    topic_info: dict[str, Any],
    all_chunks: list[Document],
    citation_anchors: list[Document],
    doc_name: str,
    llm,
    max_topics: int = 3,
    paragraph_max_chars: int = 900,
) -> dict[str, Any]:
    """Generate one short paragraph per missing topic and append to the summary.

    Unlike the global backfill (which rewrites the whole draft), this function
    issues one small LLM call per topic and appends only the validated paragraph.
    On validation failure the paragraph is discarded silently (fail-safe).

    Args:
        final_text:         Current summary body (no sources section).
        missing_topics:     List of topic IDs that need coverage.
        topic_info:         Output of extract_document_topics.
        all_chunks:         All document chunks.
        citation_anchors:   Ordered citation anchors (index 0 → [Fonte 1]).
        doc_name:           Document display name.
        llm:                Chat model instance.
        max_topics:         Maximum number of topics to process (latency guardrail).
        paragraph_max_chars: Hard char limit per generated paragraph.

    Returns:
        dict with keys:
            ``text``                — Updated summary text (may equal final_text if all fail).
            ``triggered``           — True if at least 1 topic was attempted.
            ``paragraphs_attempted``— Number of LLM calls issued.
            ``paragraphs_accepted`` — Number of paragraphs that passed validation.
            ``missing_topics_before``— Topics passed in.
            ``missing_topics_after`` — Topics still missing after accepted paragraphs.
            ``latency_ms``          — Total wall-clock ms for all LLM calls.
    """
    from docops.summarize.outline import score_topic_outline_coverage

    details = topic_info.get("topic_details", {})
    topic_anchors = get_topic_anchors(topic_info, all_chunks, max_per_topic=2)

    topics_to_process = missing_topics[:max_topics]
    skipped_topics = missing_topics[max_topics:]

    result_text = final_text
    paragraphs_attempted = 0
    paragraphs_accepted = 0
    t0_total = time.monotonic()

    for topic_id in topics_to_process:
        # Find the best anchor chunk for this topic.
        anchor_indices = topic_anchors.get(topic_id, [])
        source_label: str | None = None
        source_snippet: str | None = None
        for aidx in anchor_indices:
            if aidx >= len(all_chunks):
                continue
            chunk = all_chunks[aidx]
            # Map to citation anchor to get canonical [Fonte N] label.
            for ci, anchor in enumerate(citation_anchors):
                if (chunk.page_content or "").strip() == (anchor.page_content or "").strip():
                    source_label = f"[Fonte {ci + 1}]"
                    source_snippet = (chunk.page_content or "")[:paragraph_max_chars]
                    break
            if source_label:
                break

        if not source_label or not source_snippet:
            logger.info(
                "Micro-backfill: topic '%s' — no valid citation anchor found; skipping.",
                topic_id,
            )
            continue

        td = details.get(topic_id, {})
        topic_label = str(td.get("label", topic_id))

        prompt = DEEP_SUMMARY_MICRO_BACKFILL_PROMPT.format(
            doc_name=doc_name,
            topic_label=topic_label,
            source_label=source_label,
            source_snippet=source_snippet,
        )
        paragraphs_attempted += 1
        try:
            response = llm.invoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
            )
            paragraph_raw = response_text(response).strip()
        except Exception as exc:
            logger.warning("Micro-backfill: LLM call failed for topic '%s': %s.", topic_id, exc)
            continue

        # LLM signals insufficient evidence.
        if not paragraph_raw or paragraph_raw.strip().upper().startswith("INSUFICIENTE"):
            logger.info(
                "Micro-backfill: topic '%s' — LLM returned INSUFICIENTE; discarding.",
                topic_id,
            )
            continue

        # Truncate to hard char limit.
        paragraph = paragraph_raw[:paragraph_max_chars]

        # Validate: must contain the canonical citation.
        if source_label not in paragraph:
            logger.info(
                "Micro-backfill: topic '%s' — paragraph missing citation %s; discarding.",
                topic_id,
                source_label,
            )
            continue

        # Validate: no phantom citations beyond len(citation_anchors).
        para_clean, cit_cleanup = validate_summary_citations(paragraph, citation_anchors)
        if cit_cleanup.get("repaired"):
            logger.info(
                "Micro-backfill: topic '%s' — phantom citations removed from paragraph.",
                topic_id,
            )
        para_clean = _sanitize_non_canonical_citations(para_clean)

        # Validate only the inserted paragraph (local check, no full-document rewrite).
        _, local_grounding = validate_summary_grounding(
            para_clean,
            citation_anchors,
            threshold=0.05,
        )
        # We only care that the inserted paragraph has acceptable local grounding.
        lwr = _compute_weak_ratio(local_grounding)
        max_ceiling = float(getattr(config, "summary_max_accepted_weak_ratio", 0.5))
        if lwr > max_ceiling:
            logger.info(
                "Micro-backfill: topic '%s' — paragraph rejected (local weak_ratio=%.2f > ceiling=%.2f).",
                topic_id,
                lwr,
                max_ceiling,
            )
            continue

        # Accept: append to current summary (before sources section placeholder).
        section_header = "\n\n## Complemento Técnico\n\n" if paragraphs_accepted == 0 and "## Complemento Técnico" not in result_text else "\n\n"
        result_text = result_text + section_header + para_clean
        paragraphs_accepted += 1
        logger.info(
            "Micro-backfill: topic '%s' — paragraph accepted (%d chars).",
            topic_id,
            len(para_clean),
        )

    if skipped_topics:
        logger.info(
            "Micro-backfill: %d topic(s) skipped due to max_topics=%d limit: %s.",
            len(skipped_topics),
            max_topics,
            skipped_topics,
        )

    # Determine remaining missing topics.
    post_coverage = score_topic_outline_coverage(result_text, topic_info)
    missing_after = list(post_coverage.get("missing_topics", []))

    total_ms = round((time.monotonic() - t0_total) * 1000, 1)
    return {
        "text": result_text,
        "triggered": paragraphs_attempted > 0,
        "paragraphs_attempted": paragraphs_attempted,
        "paragraphs_accepted": paragraphs_accepted,
        "missing_topics_before": list(missing_topics),
        "missing_topics_after": missing_after,
        "skipped_topics": skipped_topics,
        "latency_ms": total_ms,
    }


def _run_topic_backfill(
    draft: str,
    topic_info: dict[str, Any],
    all_chunks: list[Document],
    citation_anchors: list[Document],
    doc_name: str,
    llm,
    max_per_topic: int = 2,
) -> str:
    """Attempt to backfill missing topics into the summary via one LLM call.

    Gathers context chunks for missing topics and asks the LLM to integrate
    coverage into the existing draft without breaking structure or citations.
    """
    # Filter to only topics actually missing from the draft.
    from docops.summarize.outline import score_topic_outline_coverage
    current_coverage = score_topic_outline_coverage(draft, topic_info)
    actually_missing = list(current_coverage.get("missing_topics", []))
    if not actually_missing:
        return draft

    # Gather anchor chunks for missing topics.
    topic_anchors = get_topic_anchors(topic_info, all_chunks, max_per_topic=max_per_topic)
    backfill_chunks: list[Document] = []
    seen_indices: set[int] = set()
    for tid in actually_missing:
        for idx in topic_anchors.get(tid, []):
            if idx not in seen_indices and idx < len(all_chunks):
                backfill_chunks.append(all_chunks[idx])
                seen_indices.add(idx)

    if not backfill_chunks:
        logger.info("Topic backfill: no anchor chunks found for missing topics.")
        return draft

    # Build context block using same numbering as citation_anchors.
    # Only include chunks that map to a valid [Fonte N] anchor; discard the rest
    # so the LLM never sees a non-canonical label in the backfill context.
    context_lines: list[str] = []
    discarded_no_anchor: int = 0
    for chunk in backfill_chunks:
        # Try to find matching anchor index.
        anchor_idx = None
        for ai, anchor in enumerate(citation_anchors):
            if (chunk.page_content or "").strip() == (anchor.page_content or "").strip():
                anchor_idx = ai + 1
                break
        if anchor_idx is None:
            discarded_no_anchor += 1
            continue
        snippet = (chunk.page_content or "")[:800]
        context_lines.append(f"[Fonte {anchor_idx}]\n{snippet}")

    if discarded_no_anchor:
        logger.info(
            "Topic backfill: %d chunk(s) discarded — no matching citation anchor.",
            discarded_no_anchor,
        )

    if not context_lines:
        logger.info("Topic backfill: all backfill chunks discarded (no anchor match); skipping LLM call.")
        return draft

    backfill_context = "\n\n---\n\n".join(context_lines)

    # Build missing topics description.
    details = topic_info.get("topic_details", {})
    topic_descs: list[str] = []
    for tid in actually_missing:
        td = details.get(tid, {})
        topic_descs.append(f"- {td.get('label', tid)} (evidência: {td.get('hits', 0)} chunks)")
    missing_description = "\n".join(topic_descs)

    prompt = DEEP_SUMMARY_TOPIC_BACKFILL_PROMPT.format(
        doc_name=doc_name,
        draft=draft,
        missing_topics_description=missing_description,
        backfill_context=backfill_context,
    )
    response = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return response_text(response)


def _build_resynthesis_feedback(
    structure_info: dict[str, Any],
    grounding_info: dict[str, Any],
    unique_sources: int,
    min_unique_sources: int,
    coverage_info: "dict[str, Any] | None" = None,
    coverage_min_score: float = 0.50,
    topic_coverage_info: "dict[str, Any] | None" = None,
    topic_coverage_min_score: float = 0.70,
    notation_info: "dict[str, Any] | None" = None,
    notation_min_score: float = 0.75,
    critical_claims_info: "dict[str, Any] | None" = None,
    critical_claims_min_score: float = 0.80,
) -> str:
    """Build concise quality diagnostics for the re-synthesis prompt.

    Args:
        structure_info:    Output of ``validate_summary_structure``.
        grounding_info:    Output of ``validate_summary_grounding``.
        unique_sources:    Number of distinct [Fonte N] used in the current text.
        min_unique_sources: Target citation diversity.
        coverage_info:     Optional output of ``score_coverage``.  When provided
            and the overall score is below ``coverage_min_score``, a coverage
            section is appended listing which content types are under-represented.
        coverage_min_score: Coverage threshold used only for labelling gaps.
    """
    weak_ratio = _compute_weak_ratio(grounding_info)
    cited_blocks = grounding_info.get("blocks_with_citations", 0)
    weak_blocks = grounding_info.get("weakly_grounded", 0)
    missing_categories = ", ".join(structure_info.get("missing_categories", [])) or "none"
    missing_heading_categories = ", ".join(
        structure_info.get("missing_heading_categories", [])
    ) or "none"
    body_fallback_categories = ", ".join(
        structure_info.get("body_fallback_categories", [])
    ) or "none"
    weak_sections = ", ".join(structure_info.get("weak_section_titles", [])) or "none"
    structure_failure_reason = (
        str(structure_info.get("structure_failure_reason", "")).strip() or "none"
    )
    closure_ok = bool(structure_info.get("closure_section_ok", False))
    lines = [
        f"- grounded blocks: weak={weak_blocks}/{cited_blocks} (ratio={weak_ratio:.2f})",
        f"- unique cited sources: {unique_sources} (target >= {min_unique_sources})",
        f"- structure valid: {bool(structure_info.get('valid'))}",
        f"- structure failure reason: {structure_failure_reason}",
        f"- missing required section categories: {missing_categories}",
        f"- missing heading categories: {missing_heading_categories}",
        f"- categories inferred from body (fallback): {body_fallback_categories}",
        f"- weak/generic sections: {weak_sections}",
        f"- closure section substantive: {closure_ok}",
    ]
    if coverage_info is not None:
        overall = coverage_info.get("overall_coverage_score", 1.0)
        lines.append(
            f"- coverage score: {overall:.2f} (target >= {coverage_min_score:.2f})"
        )
        gaps: list[str] = []
        if coverage_info.get("formula_coverage", 1.0) < 0.5:
            gaps.append("fórmulas/equações")
        if coverage_info.get("procedure_coverage", 1.0) < 0.5:
            gaps.append("algoritmos/procedimentos")
        if coverage_info.get("example_coverage", 1.0) < 0.5:
            gaps.append("exemplos")
        if coverage_info.get("concept_coverage", 1.0) < 0.5:
            gaps.append("conceitos/definições")
        if gaps:
            lines.append(f"- conteúdo sub-representado: {', '.join(gaps)}")
    return "\n".join(lines)


def resynthesize_deep_summary(
    draft: str,
    consolidated: str,
    partials: list[str],
    doc_name: str,
    citation_anchors: list[Document],
    quality_feedback: str,
    gap_contract: str,
    min_unique_sources: int,
    llm,
) -> str:
    """Run one global re-synthesis pass when quality gates fail."""
    partials_block = "\n\n".join(partials)
    context_sample = build_context_block(citation_anchors)
    prompt = DEEP_SUMMARY_RESYNTHESIS_PROMPT.format(
        doc_name=doc_name,
        draft=draft,
        consolidated=consolidated,
        partials_block=partials_block,
        context_sample=context_sample,
        quality_feedback=quality_feedback,
        gap_contract=gap_contract,
        min_unique_sources=min_unique_sources,
    )

    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        result = response_text(response)
        logger.info("Deep summary global re-synthesis completed (%d chars).", len(result))
        return result or draft
    except Exception as exc:
        logger.warning("Deep summary global re-synthesis failed: %s", exc)
        return draft


def _apply_structure_fix(draft: str, doc_name: str, llm) -> str:
    """One LLM pass to reorganize structure/cohesion without altering factual content.

    Called when a re-synthesized candidate improves grounding or source diversity
    but fails the structure validation gate (wrong heading count, missing required
    categories, or weak sections). This pass focuses exclusively on reorganizing
    the sections — it must not invent new citations or alter cited facts.

    Args:
        draft: The candidate text that failed structure validation.
        doc_name: Document file name (for prompt formatting only).
        llm: LLM instance to call.

    Returns:
        Reorganized text, or the original ``draft`` on LLM failure.
    """
    prompt = DEEP_SUMMARY_STRUCTURE_FIX_PROMPT.format(
        doc_name=doc_name,
        draft=draft,
    )
    try:
        response = llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        result = response_text(response)
        logger.info("Deep summary structure-fix pass completed (%d chars).", len(result))
        return result or draft
    except Exception as exc:
        logger.warning("Deep summary structure-fix pass failed: %s", exc)
        return draft


def _resolve_profile(profile_arg: str | None) -> str:
    """Resolve the effective execution profile.

    Priority: explicit argument > SUMMARY_DEEP_PROFILE env var > 'model_first'.
    Validates against known values; invalid values fall back to 'model_first'.
    """
    if profile_arg:
        resolved = profile_arg.strip().lower()
        if resolved in ("fast", "model_first", "strict"):
            return resolved
        # Explicit invalid value should not silently inherit env/config.
        return "model_first"
    cfg_val = str(getattr(config, "summary_deep_profile", "model_first")).strip().lower()
    if cfg_val in ("fast", "model_first", "strict"):
        return cfg_val
    return "model_first"


def run_deep_summary(
    doc_name: str,
    doc_id: str,
    user_id: int,
    include_diagnostics: bool = False,
    profile: str | None = None,
) -> dict[str, Any]:
    """Execute the full multi-step deep summary pipeline.

    Args:
        doc_name:            Document file name (used for display and metadata filtering).
        doc_id:              Document UUID from the database (preferred filter for Chroma).
        user_id:             Authenticated user ID for multi-tenant isolation.
        include_diagnostics: When True, attach full diagnostics dict to the result.
        profile:             Execution profile override: 'fast' | 'model_first' | 'strict'.
                             When None, uses SUMMARY_DEEP_PROFILE env var (default: 'model_first').

    Returns:
        Dict with keys:
            ``answer``          — Final summary text with sources section appended.
            ``sources_section`` — Formatted "Fontes:" block (also inside ``answer``).
            ``diagnostics``     — Full diagnostics (only when include_diagnostics=True).
    """
    _active_profile = _resolve_profile(profile)
    _max_corrective_passes = int(getattr(config, "summary_max_corrective_passes", 1))
    _style_polish_enabled = (
        _active_profile != "fast"
        and bool(getattr(config, "summary_style_polish_enabled", False))
    )
    # corrective_passes_used counts: deoverreach, resynthesis, backfill, extra outline-repair
    _corrective_passes_used: int = 0
    # Timeline of corrective passes executed, in order (e.g. ["micro_backfill", "deoverreach"]).
    _corrective_timeline: list[str] = []

    logger.info(
        "Deep summary pipeline started: doc='%s', doc_id=%s, user=%s, profile=%s, "
        "max_corrective_passes=%d, style_polish=%s",
        doc_name,
        doc_id,
        user_id,
        _active_profile,
        _max_corrective_passes,
        _style_polish_enabled,
    )
    _start_ts = time.monotonic()
    _latency_budget_s = max(1.0, float(getattr(config, "summary_latency_budget_seconds", 300.0)))

    # Per-stage timing (ms)
    _stage_timings: dict[str, float] = {}

    def _t(label: str):
        """Context manager / helper to measure stage elapsed time in ms."""
        class _Timer:
            def __init__(self, lbl: str):
                self._lbl = lbl
                self._t0 = 0.0
            def __enter__(self):
                self._t0 = time.monotonic()
                return self
            def __exit__(self, *_):
                _stage_timings[self._lbl] = round((time.monotonic() - self._t0) * 1000, 1)
        return _Timer(label)

    def _latency_budget_exceeded(reserve_s: float = 0.0) -> bool:
        elapsed = time.monotonic() - _start_ts
        return elapsed >= max(0.0, _latency_budget_s - max(0.0, reserve_s))

    def _corrective_budget_available() -> bool:
        """Return True when another corrective pass can be started."""
        if _active_profile == "fast":
            return False
        return _corrective_passes_used < _max_corrective_passes

    def _remaining_corrective_passes() -> int:
        return max(0, _max_corrective_passes - _corrective_passes_used)

    def _consume_corrective_pass(pass_name: str) -> None:
        nonlocal _corrective_passes_used
        _corrective_passes_used += 1
        _corrective_timeline.append(pass_name)
        logger.info(
            "Corrective pass consumed: %s (%d/%d).",
            pass_name,
            _corrective_passes_used,
            _max_corrective_passes,
        )

    # ── 1. Collect ────────────────────────────────────────────────────────────
    with _t("collect"):
        chunks = collect_ordered_chunks(doc_name, doc_id, user_id)
    if not chunks:
        logger.warning("No chunks found for doc='%s'.", doc_name)
        result = {
            "answer": (
                f"Não foram encontrados trechos indexados para o documento **{doc_name}**. "
                "Verifique se o documento foi ingerido corretamente."
            ),
            "sources_section": "",
        }
        if include_diagnostics:
            result["diagnostics"] = {"error": "no_chunks_found", "doc_name": doc_name}
        return result

    logger.info("Deep summary: %d chunks collected.", len(chunks))

    # ── 2. Clean ─────────────────────────────────────────────────────────────
    # Keep raw chunks for noisy-extraction heuristics used by adaptive grounding.
    raw_chunks = chunks
    with _t("clean"):
        chunks = _clean_chunks(chunks)

    # ── Model-first path (primary) ───────────────────────────────────────────
    # Keep orchestration minimal (single synthesis call) while preserving
    # source-faithful coverage via deterministic topic/outline contracts.
    if _active_profile == "model_first":
        _, _, section_threshold = _get_tuning()
        section_cov_before = sum(
            1
            for c in chunks
            if c.metadata.get("section_path") or c.metadata.get("section_title")
        ) / max(1, len(chunks))
        pdf_chunks_ratio = (
            sum(
                1
                for c in chunks
                if str(c.metadata.get("file_type", "")).lower() == "pdf"
            )
            / max(1, len(chunks))
        )
        if pdf_chunks_ratio >= 0.5 and section_cov_before < section_threshold:
            infer_pdf_structure(chunks)
        pdf_outline_entries = extract_pdf_outline(chunks)

        facet_min_hits = int(getattr(config, "summary_facet_min_hits", 2))
        doc_profile = build_document_profile(chunks, min_hits=facet_min_hits)
        topic_info = extract_document_topics(chunks, major_topic_min_hits=2)
        must_cover_topics = list(topic_info.get("must_cover_topics", []))
        facet_contract = _format_doc_profile_contract(doc_profile)
        topic_contract = topic_info.get("outline_text", "")
        coverage_contract = facet_contract
        if topic_contract:
            coverage_contract = f"{facet_contract}\n\n{topic_contract}"

        with _t("group"):
            groups = group_chunks(chunks, infer_pdf=False)
        logger.info("Deep summary (model_first): %d groups formed.", len(groups))

        llm_complex = _get_llm(route="complex", temperature=0.2)
        _stage_timings["partials"] = 0.0
        _stage_timings["consolidate"] = 0.0
        _stage_timings["style_polish"] = 0.0

        max_anchors = int(getattr(config, "summary_max_sources", 12))
        with _t("select_anchors"):
            citation_anchors = _select_citation_anchors(
                chunks,
                groups,
                max_anchors=max_anchors,
                topic_info=topic_info,
            )
        if not citation_anchors:
            citation_anchors = list(chunks[: max(1, min(max_anchors, len(chunks)))])
        logger.info(
            "Deep summary (model_first): %d citation anchor(s) selected (valid range: 1..%d).",
            len(citation_anchors),
            len(citation_anchors),
        )

        _consolidated_hint = (
            "Síntese evidence-first, sem extrapolar além das fontes. "
            f"Tópicos obrigatórios detectados: {', '.join(must_cover_topics) if must_cover_topics else 'nenhum'}."
        )
        with _t("finalize"):
            final_text = finalize_deep_summary(
                consolidated=_consolidated_hint,
                partials=[],
                doc_name=doc_name,
                citation_anchors=citation_anchors,
                coverage_contract=coverage_contract,
                llm=llm_complex,
            )

        final_text = _strip_sources_section(final_text)
        final_text = _sanitize_inline_source_noise(final_text)
        final_text = _sanitize_non_canonical_citations(final_text)
        final_text, citation_validation = validate_summary_citations(
            final_text, citation_anchors
        )

        base_grounding_threshold = float(
            getattr(config, "summary_grounding_threshold", 0.20)
        )
        grounding_threshold = _resolve_grounding_threshold(
            raw_chunks,
            chunks,
            base_threshold=base_grounding_threshold,
        )
        with _t("grounding"):
            final_text, grounding_info = validate_summary_grounding(
                final_text,
                citation_anchors,
                grounding_threshold,
                llm=None,  # model_first intentionally avoids rewrite-repairs
            )

        final_text = clean_summary_output(final_text)
        final_text = _sanitize_non_canonical_citations(final_text)
        final_text, _ = validate_summary_citations(final_text, citation_anchors)
        body_text = final_text
        used_source_indices = _extract_used_citation_indices(
            body_text, len(citation_anchors)
        )
        sources_section = build_anchor_sources_section(
            citation_anchors,
            source_indices=used_source_indices,
        )
        if sources_section:
            final_text = body_text.rstrip() + "\n\n" + sources_section

        structure_min_chars = int(getattr(config, "summary_structure_min_chars", 160))
        structure_info = validate_summary_structure(
            body_text,
            min_section_chars=structure_min_chars,
        )
        weak_ratio = _compute_weak_ratio(grounding_info)
        outline_coverage = score_topic_outline_coverage(body_text, topic_info)
        formula_mode = str(getattr(config, "summary_formula_mode", "conservative"))
        claim_risk = classify_claim_risks(body_text, citation_anchors)
        claim_risk = check_formula_mode(claim_risk, citation_anchors, formula_mode)
        inference = compute_inference_density(claim_risk)

        blocking_reasons: list[str] = []
        if not bool(structure_info.get("valid", False)):
            blocking_reasons.append(
                "structure_invalid: "
                f"{str(structure_info.get('structure_failure_reason', '')).strip() or 'unknown'}"
            )
        missing_topics = list(outline_coverage.get("missing_topics", []))
        if must_cover_topics and missing_topics:
            blocking_reasons.append(
                f"outline_missing_topics_not_allowed: missing={missing_topics}"
            )
        if int(claim_risk.get("unsupported_high_risk_count", 0)) > 0:
            blocking_reasons.append(
                f"unsupported_high_risk_claims: count={int(claim_risk.get('unsupported_high_risk_count', 0))}"
            )
        if not bool(inference.get("inference_gate_passed", True)):
            blocking_reasons.append(
                f"inference_density_exceeded: {float(inference.get('inference_density', 0.0)):.4f}"
            )

        diagnostics = {
            "profile_used": _active_profile,
            "mode": "model_first",
            "document_profile": {
                "required_facets": list(doc_profile.get("required_facets", [])),
                "pdf_outline_sections": len(pdf_outline_entries),
            },
            "outline_coverage": {
                "score": float(outline_coverage.get("overall_score", 1.0)),
                "must_cover_topics": list(outline_coverage.get("must_cover_topics", [])),
                "missing_topics": missing_topics,
                "covered_topics": list(outline_coverage.get("covered_topics", [])),
            },
            "citations": {
                "anchors_total": len(citation_anchors),
                "inline_found": int(citation_validation.get("citations_found", 0)),
                "phantom_indices": list(citation_validation.get("phantom_indices", [])),
                "unique_sources_used": len(used_source_indices),
            },
            "grounding": {
                "threshold": grounding_threshold,
                "blocks_with_citations": int(grounding_info.get("blocks_with_citations", 0)),
                "weakly_grounded": int(grounding_info.get("weakly_grounded", 0)),
                "repaired_blocks": int(grounding_info.get("repaired_blocks", 0)),
                "weak_ratio": round(weak_ratio, 4),
            },
            "structure": {
                "valid": bool(structure_info.get("valid", False)),
                "section_count": int(structure_info.get("section_count", 0)),
                "structure_failure_reason": str(
                    structure_info.get("structure_failure_reason", "")
                ),
            },
            "claim_risk": {
                "unsupported_high_risk_count": int(
                    claim_risk.get("unsupported_high_risk_count", 0)
                ),
                "unsupported_high_risk_low_info_only_count": int(
                    claim_risk.get("unsupported_high_risk_low_info_only_count", 0)
                ),
                "formula_mode": formula_mode,
            },
            "inference_density": {
                "inference_density": float(inference.get("inference_density", 0.0)),
                "inference_threshold": float(inference.get("inference_threshold", 0.0)),
                "inference_gate_passed": bool(inference.get("inference_gate_passed", True)),
            },
            "corrective_timeline": [],
            "corrective_passes_used": 0,
            "max_corrective_passes": 0,
            "style_polish_enabled": False,
            "deoverreach": {"enabled": False, "triggered": False, "accepted": False},
            "resynthesis": {"enabled": False, "triggered": False, "accepted": False},
            "micro_backfill": {"enabled": False, "triggered": False, "accepted": False},
            "early_micro_backfill": {"enabled": False, "triggered": False, "accepted": False},
            "final": {
                "accepted": len(blocking_reasons) == 0,
                "blocking_reasons": list(blocking_reasons),
                "missing_topics": missing_topics,
            },
        }

        _total_ms = round((time.monotonic() - _start_ts) * 1000, 1)
        diagnostics["latency"] = {
            "total_ms": _total_ms,
            "stage_timings_ms": dict(_stage_timings),
        }
        logger.info(
            "Deep summary model_first completed for doc='%s' in %.1fs.",
            doc_name,
            _total_ms / 1000,
        )
        result = {
            "answer": final_text,
            "sources_section": sources_section,
        }
        if include_diagnostics:
            result["diagnostics"] = diagnostics
        return result

    # Enrich PDF structure BEFORE topic extraction so outline topics can use
    # inferred section_title/section_path metadata.
    _, _, section_threshold = _get_tuning()
    section_cov_before = sum(
        1 for c in chunks if c.metadata.get("section_path") or c.metadata.get("section_title")
    ) / max(1, len(chunks))
    pdf_chunks_ratio = (
        sum(1 for c in chunks if str(c.metadata.get("file_type", "")).lower() == "pdf")
        / max(1, len(chunks))
    )
    if pdf_chunks_ratio >= 0.5 and section_cov_before < section_threshold:
        infer_pdf_structure(chunks)
    pdf_outline_entries = extract_pdf_outline(chunks)
    if pdf_outline_entries:
        logger.info(
            "Deep summary: %d PDF outline section(s) inferred before topic extraction.",
            len(pdf_outline_entries),
        )
    facet_min_hits = int(getattr(config, "summary_facet_min_hits", 2))
    doc_profile = build_document_profile(chunks, min_hits=facet_min_hits)

    # ── 2b. Topic outline extraction ─────────────────────────────────────────
    topic_info = extract_document_topics(chunks, major_topic_min_hits=2)
    must_cover_topics = topic_info.get("must_cover_topics", [])
    if must_cover_topics:
        logger.info(
            "Deep summary: %d must-cover topics detected: %s.",
            len(must_cover_topics),
            ", ".join(must_cover_topics),
        )
    # Build coverage contract combining facet profile + topic outline.
    facet_contract = _format_doc_profile_contract(doc_profile)
    topic_contract = topic_info.get("outline_text", "")
    coverage_contract = facet_contract
    if topic_contract:
        coverage_contract = f"{facet_contract}\n\n{topic_contract}"

    # ── 3. Group ─────────────────────────────────────────────────────────────
    with _t("group"):
        groups = group_chunks(chunks, infer_pdf=False)
    logger.info("Deep summary: %d groups formed.", len(groups))

    llm_complex = _get_llm(route="complex", temperature=0.2)
    llm_cheap = _get_llm(route="cheap", temperature=0.2)

    # ── 4. Partial summaries ─────────────────────────────────────────────────
    with _t("partials"):
        partials = summarize_groups(groups, doc_name, llm_cheap)
    logger.info("Deep summary: %d partial summaries generated.", len(partials))

    # ── 5. Consolidation ─────────────────────────────────────────────────────
    with _t("consolidate"):
        consolidated = consolidate_summaries(partials, doc_name, llm_complex)
    logger.info("Deep summary: consolidation complete.")

    # ── 6. Select citation anchors ────────────────────────────────────────────
    # These chunks become [Fonte 1]..[Fonte N] in BOTH the synthesis context
    # and the final Fontes: section. Using a single list guarantees that
    # [Fonte N] in the body always corresponds to [Fonte N] in the sources.
    max_anchors = getattr(config, "summary_max_sources", 12)
    with _t("select_anchors"):
        citation_anchors = _select_citation_anchors(
            chunks, groups, max_anchors=max_anchors, topic_info=topic_info,
        )
    logger.info(
        "Deep summary: %d citation anchor(s) selected (valid range: 1..%d).",
        len(citation_anchors),
        len(citation_anchors),
    )

    # ── 6a. Build evidence-first context for final synthesis ──────────────────
    # Instead of using only the citation_anchors as context (compressed),
    # build a richer context that includes:
    #   - one representative chunk per must-cover topic (from topic anchors)
    #   - all citation anchors (for numbering consistency)
    # This reduces the need for corrective passes by giving the LLM better
    # evidence upfront. Citation anchors remain the SOLE numbering source.
    _topic_anchors: list = []
    if must_cover_topics:
        try:
            _topic_anchors = get_topic_anchors(chunks, topic_info, citation_anchors, max_extra=6)
        except Exception as _ta_exc:
            logger.debug("topic_anchors extraction failed (non-fatal): %s", _ta_exc)

    # Merge: topic_anchors first (for prominence), then citation_anchors deduplicated.
    # The LLM receives both, but [Fonte N] numbering is still built from citation_anchors only.
    _extra_anchor_texts: set[str] = {
        (c.page_content or "")[:120] for c in citation_anchors
    }
    _evidence_chunks: list = list(citation_anchors)
    for _ta in _topic_anchors:
        _ta_key = (_ta.page_content or "")[:120]
        if _ta_key not in _extra_anchor_texts:
            _evidence_chunks.append(_ta)
            _extra_anchor_texts.add(_ta_key)

    # ── 6b. Final synthesis ───────────────────────────────────────────────────
    with _t("finalize"):
        final_text = finalize_deep_summary(
            consolidated,
            partials,
            doc_name,
            citation_anchors,
            coverage_contract,
            llm_complex,
        )
    if _style_polish_enabled:
        with _t("style_polish"):
            final_text = polish_deep_summary_style(final_text, doc_name, llm_complex)
    else:
        _stage_timings["style_polish"] = 0.0
    final_text = _strip_sources_section(final_text)
    final_text = _sanitize_inline_source_noise(final_text)

    # ── 6d. Citation validation ───────────────────────────────────────────────
    # Removes phantom [Fonte N] references (N > len(citation_anchors)) and logs
    # whether the synthesis produced any inline citations at all.
    final_text, citation_validation = validate_summary_citations(final_text, citation_anchors)
    logger.info(
        "Deep summary citation validation: found=%d inline citation(s), "
        "phantoms=%d, repaired=%s, no_citations=%s.",
        citation_validation["citations_found"],
        len(citation_validation["phantom_indices"]),
        citation_validation["repaired"],
        citation_validation["no_citations"],
    )

    # ── 6e. Semantic grounding ────────────────────────────────────────────────
    # Heuristic check: for every cited block, measure token overlap with the
    # cited anchor texts. Blocks below threshold are flagged (and optionally
    # repaired when SUMMARY_GROUNDING_REPAIR=true).
    base_grounding_threshold = float(getattr(config, "summary_grounding_threshold", 0.20))
    grounding_threshold = _resolve_grounding_threshold(
        raw_chunks,
        chunks,
        base_threshold=base_grounding_threshold,
    )
    repair_enabled = getattr(config, "summary_grounding_repair", False)
    with _t("grounding"):
        final_text, grounding_info = validate_summary_grounding(
            final_text,
            citation_anchors,
            threshold=grounding_threshold,
            llm=llm_cheap if repair_enabled else None,
        )
    logger.info(
        "Deep summary grounding: %d block(s) with citations checked, "
        "%d weakly grounded, %d repaired.",
        grounding_info["blocks_with_citations"],
        grounding_info["weakly_grounded"],
        grounding_info["repaired_blocks"],
    )

    # Grounding repair can reintroduce out-of-range citations; validate again.
    final_text, post_grounding_validation = validate_summary_citations(
        final_text,
        citation_anchors,
    )
    if post_grounding_validation["repaired"]:
        logger.warning(
            "Deep summary post-grounding citation cleanup: removed %d phantom citation(s).",
            len(post_grounding_validation["phantom_indices"]),
        )
    final_text = _sanitize_inline_source_noise(final_text)

    # ── 7. Clean output ──────────────────────────────────────────────────────
    final_text = clean_summary_output(final_text)
    final_text = _strip_sources_section(final_text)
    final_text = _sanitize_inline_source_noise(final_text)

    # ── 8. Sources section — only sources actually cited in body ─────────────
    # Keep original numbering labels ([Fonte N]) and render only entries that
    # appear in the final answer text for better traceability.
    structure_min_chars = int(getattr(config, "summary_structure_min_chars", 160))
    min_unique_sources_cfg = int(getattr(config, "summary_min_unique_sources", 7))
    n_anchors = len(citation_anchors)
    n_groups = len(groups)
    if n_anchors > 0:
        # Adaptive diversity target: at most the configured value, but also at
        # most 50% of available anchors (rounded up) and at most the number of
        # groups.  This prevents hard-fail when the document is small or has
        # few logical sections.
        adaptive_cap = max(1, -(-n_anchors // 2))  # ceil(n_anchors / 2)
        group_cap = max(1, n_groups) if n_groups > 0 else adaptive_cap
        min_unique_sources = min(min_unique_sources_cfg, adaptive_cap, group_cap)
        min_unique_sources = max(1, min_unique_sources)
    else:
        min_unique_sources = 0
    logger.info(
        "Deep summary diversity target: %d unique sources "
        "(config=%d, anchors=%d, groups=%d, adaptive_cap=%d).",
        min_unique_sources,
        min_unique_sources_cfg,
        n_anchors,
        n_groups,
        adaptive_cap if n_anchors > 0 else 0,
    )

    # Validate structure and prune weak sections before building the final sources list.
    final_text, structure_pass = _postprocess_deep_summary_text(
        final_text,
        citation_anchors,
        grounding_threshold=grounding_threshold,
        llm=llm_cheap,
        repair_enabled=False,
        structure_min_chars=structure_min_chars,
    )
    structure_info = structure_pass["structure_info"]
    used_source_indices = list(structure_pass["used_source_indices"])
    dropped_weak_sections = int(structure_pass["dropped_weak_sections"])
    if structure_pass["dropped_weak_sections"] > 0:
        logger.info(
            "Deep summary structure: dropped %d weak/generic section(s).",
            structure_pass["dropped_weak_sections"],
        )

    # ── Coverage gate ─────────────────────────────────────────────────────────
    # Detect content signal types in source chunks; score how well the final
    # summary covers them.  Low coverage is an additional trigger for global
    # re-synthesis, with explicit coverage feedback included in the prompt.
    coverage_gate_enabled = bool(getattr(config, "summary_coverage_gate_enabled", True))
    coverage_signals: dict[str, Any] = detect_coverage_signals(chunks)
    configured_profile = str(getattr(config, "summary_coverage_profile", "auto"))
    coverage_profile = resolve_coverage_profile(
        doc_name,
        coverage_signals,
        configured_profile=configured_profile,
    )
    current_coverage: dict[str, Any] = score_coverage(
        final_text,
        coverage_signals,
        coverage_profile=coverage_profile,
    )
    min_score_override = getattr(config, "summary_coverage_min_score_override", None)
    if min_score_override is not None:
        coverage_min_score = float(min_score_override)
    else:
        coverage_min_score = float(
            coverage_profile.get(
                "min_score",
                getattr(config, "summary_coverage_min_score", 0.50),
            )
        )

    logger.info(
        "Deep summary coverage profile: %s (%s).",
        coverage_profile.get("name"),
        coverage_profile.get("reason"),
    )
    logger.info(
        "Deep summary coverage: score=%.2f "
        "(formula=%.2f, procedure=%.2f, example=%.2f, concept=%.2f) "
        "[formula_chunks=%d, procedure_chunks=%d, example_chunks=%d, concept_chunks=%d].",
        current_coverage["overall_coverage_score"],
        current_coverage["formula_coverage"],
        current_coverage["procedure_coverage"],
        current_coverage["example_coverage"],
        current_coverage["concept_coverage"],
        coverage_signals["formula_chunks"],
        coverage_signals["procedure_chunks"],
        coverage_signals["example_chunks"],
        coverage_signals["concept_chunks"],
    )
    # Global re-synthesis gate: weak grounding, invalid structure, poor source diversity,
    # or insufficient content coverage.
    weak_ratio_threshold = float(
        getattr(config, "summary_resynthesis_weak_block_ratio", 0.50)
    )
    weak_ratio = _compute_weak_ratio(grounding_info)
    resynthesis_enabled = bool(getattr(config, "summary_resynthesis_enabled", True))

    topic_gate_enabled = bool(getattr(config, "summary_facet_gate_enabled", True))
    topic_gate_enabled = bool(topic_gate_enabled and coverage_gate_enabled)
    topic_min_score = float(getattr(config, "summary_facet_min_score", 0.70))
    current_topic_coverage = score_topic_coverage(final_text, doc_profile)

    # Topic outline coverage (stronger than broad facet check).
    current_outline_coverage = score_topic_outline_coverage(final_text, topic_info)

    notation_gate_enabled = bool(getattr(config, "summary_notation_gate_enabled", True))
    notation_gate_enabled = bool(notation_gate_enabled and coverage_gate_enabled)
    notation_min_score = float(getattr(config, "summary_notation_min_score", 0.75))
    current_notation = assess_notation_fidelity(final_text, doc_profile)

    claims_gate_enabled = bool(getattr(config, "summary_claim_gate_enabled", True))
    claims_gate_enabled = bool(claims_gate_enabled and coverage_gate_enabled)
    claims_min_score = float(getattr(config, "summary_claim_min_score", 0.80))
    current_critical_claims = evaluate_critical_claim_coverage(final_text, doc_profile)

    rubric_gate_enabled = bool(getattr(config, "summary_rubric_gate_enabled", True))
    rubric_gate_enabled = bool(rubric_gate_enabled and coverage_gate_enabled)
    rubric_min_score = float(getattr(config, "summary_rubric_min_score", 0.72))
    current_rubric = compute_summary_rubric(
        structure_valid=bool(structure_info.get("valid", False)),
        weak_ratio=weak_ratio,
        unique_sources=len(used_source_indices),
        min_unique_sources=min_unique_sources,
        coverage_score=float(current_coverage.get("overall_coverage_score", 1.0)),
        facet_score=float(current_topic_coverage.get("overall_score", 1.0)),
        claims_score=float(current_critical_claims.get("score", 1.0)),
        notation_score=float(current_notation.get("score", 1.0)),
        outline_score=float(current_outline_coverage.get("overall_score", 1.0)),
    )
    logger.info(
        "Deep summary profile coverage: facet_score=%.2f required=%d missing=%d; "
        "notation_score=%.2f issues=%d; claims_score=%.2f missing=%d; rubric=%.2f.",
        current_topic_coverage.get("overall_score", 1.0),
        len(current_topic_coverage.get("required_facets", [])),
        len(current_topic_coverage.get("missing_facets", [])),
        current_notation.get("score", 1.0),
        len(current_notation.get("issues", [])),
        current_critical_claims.get("score", 1.0),
        len(current_critical_claims.get("missing_facets", [])),
        current_rubric.get("overall_score", 1.0),
    )
    claim_local_repair_enabled = bool(
        getattr(config, "summary_claim_local_repair_enabled", True)
    )
    claim_local_repair_info: dict[str, Any] = {
        "enabled": claim_local_repair_enabled,
        "attempted": 0,
        "repaired": 0,
        "facets_repaired": [],
    }
    if (
        claims_gate_enabled
        and claim_local_repair_enabled
        and bool(current_critical_claims.get("missing_facets"))
    ):
        local_text, local_info = _repair_missing_critical_claims(
            final_text,
            list(current_critical_claims.get("missing_facets", [])),
            citation_anchors,
        )
        claim_local_repair_info.update(local_info)
        if local_text != final_text:
            logger.info(
                "Deep summary critical-claim local repair: repaired=%d/%d facets (%s).",
                int(local_info.get("repaired", 0)),
                int(local_info.get("attempted", 0)),
                ", ".join(local_info.get("facets_repaired", [])) or "none",
            )
            final_text, local_pass = _postprocess_deep_summary_text(
                local_text,
                citation_anchors,
                grounding_threshold=grounding_threshold,
                llm=llm_cheap,
                repair_enabled=repair_enabled,
                structure_min_chars=structure_min_chars,
            )
            structure_info = local_pass["structure_info"]
            grounding_info = local_pass["grounding_info"]
            used_source_indices = list(local_pass["used_source_indices"])
            dropped_weak_sections = int(local_pass.get("dropped_weak_sections", dropped_weak_sections))
            weak_ratio = _compute_weak_ratio(grounding_info)

            current_coverage = score_coverage(
                final_text,
                coverage_signals,
                coverage_profile=coverage_profile,
            )
            current_topic_coverage = score_topic_coverage(final_text, doc_profile)
            current_outline_coverage = score_topic_outline_coverage(final_text, topic_info)
            current_notation = assess_notation_fidelity(final_text, doc_profile)
            current_critical_claims = evaluate_critical_claim_coverage(final_text, doc_profile)
            current_rubric = compute_summary_rubric(
                structure_valid=bool(structure_info.get("valid", False)),
                weak_ratio=weak_ratio,
                unique_sources=len(used_source_indices),
                min_unique_sources=min_unique_sources,
                coverage_score=float(current_coverage.get("overall_coverage_score", 1.0)),
                facet_score=float(current_topic_coverage.get("overall_score", 1.0)),
                claims_score=float(current_critical_claims.get("score", 1.0)),
                notation_score=float(current_notation.get("score", 1.0)),
                outline_score=float(current_outline_coverage.get("overall_score", 1.0)),
            )

    # ── Claim-risk + inference-density fidelity check ────────────────────────
    # Runs before resynthesis so the de-overreach pass can clean the draft first.
    _formula_mode = str(getattr(config, "summary_formula_mode", "conservative"))
    current_claim_risk = classify_claim_risks(final_text, citation_anchors)
    current_claim_risk = check_formula_mode(
        current_claim_risk, citation_anchors, _formula_mode
    )
    current_inference = compute_inference_density(current_claim_risk)

    _current_outline_missing = list(current_outline_coverage.get("missing_topics", []))
    _current_outline_must_cover = list(current_outline_coverage.get("must_cover_topics", []))
    _reserve_must_cover_pass_enabled = bool(
        getattr(config, "summary_strict_reserve_pass_for_must_cover", True)
    )
    _reserve_last_pass_for_must_cover = bool(
        _reserve_must_cover_pass_enabled
        and _active_profile == "strict"
        and _current_outline_must_cover
        and _current_outline_missing
        and _remaining_corrective_passes() <= 1
    )
    if _reserve_last_pass_for_must_cover:
        logger.info(
            "Corrective scheduler: reserving last corrective pass for must-cover topics "
            "(missing=%s, remaining_passes=%d).",
            _current_outline_missing,
            _remaining_corrective_passes(),
        )

    # ── Early micro-backfill (backfill-before-deoverreach) ────────────────────
    # When summary_backfill_before_deoverreach=True (default) and there are
    # missing must-cover topics, run micro-backfill FIRST so that the limited
    # corrective budget is not consumed by de-overreach/resynthesis before topic
    # coverage is addressed. This reduces final_accepted=False cases caused by
    # missing_topics when max_corrective_passes=1 in strict profile.
    #
    # max_accepted_weak_ratio is also used later in the resynthesis block; we
    # define it here so the early backfill ceiling check can use it.
    max_accepted_weak_ratio = float(
        getattr(config, "summary_resynthesis_max_accepted_weak_ratio", 0.35)
    )
    _backfill_before_deoverreach = (
        _active_profile != "fast"
        and bool(getattr(config, "summary_backfill_before_deoverreach", True))
    )
    _early_micro_backfill_enabled = bool(getattr(config, "summary_micro_backfill_enabled", True))
    _early_micro_backfill_max_topics = int(getattr(config, "summary_micro_backfill_max_topics", 3))
    _early_micro_backfill_para_max = int(
        getattr(config, "summary_micro_backfill_paragraph_max_chars", 900)
    )
    early_backfill_info: dict[str, Any] = {
        "triggered": False,
        "accepted": False,
        "missing_before": [],
        "missing_after": [],
        "skipped_reason": None,
        "paragraphs_attempted": 0,
        "paragraphs_accepted": 0,
        "latency_ms": 0.0,
    }
    _early_backfill_ran = False
    if _backfill_before_deoverreach and _current_outline_missing and _current_outline_must_cover:
        if not _early_micro_backfill_enabled:
            early_backfill_info["skipped_reason"] = "micro_backfill_disabled"
            logger.info(
                "Early micro-backfill skipped: micro_backfill disabled "
                "(missing must-cover topics=%s).",
                _current_outline_missing,
            )
        elif not _corrective_budget_available():
            early_backfill_info["skipped_reason"] = "corrective_budget_exhausted"
            logger.info(
                "Early micro-backfill skipped: corrective budget exhausted "
                "(passes_used=%d/%d, missing=%s).",
                _corrective_passes_used,
                _max_corrective_passes,
                _current_outline_missing,
            )
        elif _latency_budget_exceeded(reserve_s=50.0):
            early_backfill_info["skipped_reason"] = "latency_budget_exhausted"
            logger.info(
                "Early micro-backfill skipped: latency budget exhausted "
                "(elapsed=%.1fs, budget=%.1fs).",
                time.monotonic() - _start_ts,
                _latency_budget_s,
            )
        else:
            _early_backfill_ran = True
            early_backfill_info["triggered"] = True
            early_backfill_info["missing_before"] = list(_current_outline_missing)
            logger.info(
                "Early micro-backfill triggered (backfill-before-deoverreach): "
                "%d missing must-cover topic(s): %s (corrective_pass=%d/%d, max_topics=%d).",
                len(_current_outline_missing),
                _current_outline_missing,
                _corrective_passes_used + 1,
                _max_corrective_passes,
                _early_micro_backfill_max_topics,
            )
            try:
                with _t("early_micro_backfill"):
                    _early_micro_result = _run_micro_topic_backfill(
                        final_text=final_text,
                        missing_topics=_current_outline_missing,
                        topic_info=topic_info,
                        all_chunks=chunks,
                        citation_anchors=citation_anchors,
                        doc_name=doc_name,
                        llm=llm_cheap,
                        max_topics=_early_micro_backfill_max_topics,
                        paragraph_max_chars=_early_micro_backfill_para_max,
                    )
                early_backfill_info["paragraphs_attempted"] = _early_micro_result[
                    "paragraphs_attempted"
                ]
                early_backfill_info["paragraphs_accepted"] = _early_micro_result[
                    "paragraphs_accepted"
                ]
                early_backfill_info["missing_after"] = _early_micro_result["missing_topics_after"]
                early_backfill_info["latency_ms"] = _early_micro_result["latency_ms"]

                if _early_micro_result["paragraphs_accepted"] > 0:
                    _early_new_text = _early_micro_result["text"]
                    _early_new_text = _sanitize_non_canonical_citations(_early_new_text)
                    _early_new_text, _ = validate_summary_citations(
                        _early_new_text, citation_anchors
                    )
                    _early_new_text, _early_grounding = validate_summary_grounding(
                        _early_new_text, citation_anchors, grounding_threshold
                    )
                    _early_bf_weak_ratio = _compute_weak_ratio(_early_grounding)
                    _early_ceiling_exceeded = _early_bf_weak_ratio > max_accepted_weak_ratio
                    if _early_ceiling_exceeded:
                        early_backfill_info["accepted"] = False
                        early_backfill_info["skipped_reason"] = "absolute_weak_ratio_exceeded"
                        logger.warning(
                            "Early micro-backfill rejected: absolute weak_ratio ceiling exceeded "
                            "(bf_weak_ratio=%.2f > ceiling=%.2f).",
                            _early_bf_weak_ratio,
                            max_accepted_weak_ratio,
                        )
                    else:
                        final_text = _early_new_text
                        grounding_info = _early_grounding
                        weak_ratio = _early_bf_weak_ratio
                        used_source_indices = _extract_used_citation_indices(
                            final_text, len(citation_anchors)
                        )
                        early_backfill_info["accepted"] = True
                        _consume_corrective_pass("micro_backfill_early")
                        logger.info(
                            "Early micro-backfill accepted: %d/%d paragraph(s), "
                            "missing topics %d → %d, weak_ratio %.2f → %.2f.",
                            _early_micro_result["paragraphs_accepted"],
                            _early_micro_result["paragraphs_attempted"],
                            len(_current_outline_missing),
                            len(_early_micro_result["missing_topics_after"]),
                            _compute_weak_ratio(grounding_info),
                            _early_bf_weak_ratio,
                        )
                        # Recalculate metrics so deoverreach/resynthesis see updated state.
                        current_outline_coverage = score_topic_outline_coverage(
                            final_text, topic_info
                        )
                        _current_outline_missing = list(
                            current_outline_coverage.get("missing_topics", [])
                        )
                        _current_outline_must_cover = list(
                            current_outline_coverage.get("must_cover_topics", [])
                        )
                        current_claim_risk = classify_claim_risks(final_text, citation_anchors)
                        current_claim_risk = check_formula_mode(
                            current_claim_risk, citation_anchors, _formula_mode
                        )
                        current_inference = compute_inference_density(current_claim_risk)
                        # Re-evaluate reserve flag with updated missing topics.
                        _reserve_last_pass_for_must_cover = bool(
                            _reserve_must_cover_pass_enabled
                            and _active_profile == "strict"
                            and _current_outline_must_cover
                            and _current_outline_missing
                            and _remaining_corrective_passes() <= 1
                        )
                        logger.info(
                            "Early micro-backfill: metrics recalculated — "
                            "missing_topics=%s, inference_density=%.4f, "
                            "reserve_last_pass=%s.",
                            _current_outline_missing,
                            current_inference["inference_density"],
                            _reserve_last_pass_for_must_cover,
                        )
                else:
                    logger.info(
                        "Early micro-backfill: no paragraphs accepted (%d attempted). "
                        "Corrective pass NOT consumed.",
                        _early_micro_result["paragraphs_attempted"],
                    )
                    early_backfill_info["skipped_reason"] = "no_paragraphs_accepted"
            except Exception as _e_early_bf:
                logger.warning(
                    "Early micro-backfill failed with exception: %s. Continuing.",
                    _e_early_bf,
                )
                early_backfill_info["skipped_reason"] = f"exception: {_e_early_bf}"

    # ── De-overreach rewrite pass ─────────────────────────────────────────────
    # Triggered when inference density is too high, unsupported high-risk claims
    # are detected, or formula claims lack math backing (conservative mode).
    # In 'fast' profile or when corrective budget is exhausted: always skipped.
    # Mutually exclusive with resynthesis: if deoverreach runs and is accepted,
    # resynthesis will be skipped for this run.
    _deoverreach_trigger = (
        not current_inference["inference_gate_passed"]
        or current_claim_risk["unsupported_high_risk_count"] > 0
        or (
            _formula_mode == "conservative"
            and current_claim_risk["formula_claims_downgraded_to_concept"] > 0
        )
    )
    deoverreach_info: dict[str, Any] = {
        "triggered": _deoverreach_trigger,
        "accepted": False,
        "pass_consumed": False,
        "inference_density_before": current_inference["inference_density"],
        "inference_density_after": current_inference["inference_density"],
        "unsupported_claims_before": current_inference["unsupported_claims_count"],
        "skipped_reason": None,
    }
    if _deoverreach_trigger and _reserve_last_pass_for_must_cover:
        deoverreach_info["skipped_reason"] = "reserved_for_must_cover_topics"
        logger.info(
            "De-overreach pass skipped: %s (missing must-cover topics=%s, profile=%s).",
            deoverreach_info["skipped_reason"],
            _current_outline_missing,
            _active_profile,
        )
        _deoverreach_trigger = False
    if _deoverreach_trigger and not _corrective_budget_available():
        deoverreach_info["skipped_reason"] = (
            "profile_fast" if _active_profile == "fast" else "corrective_budget_exhausted"
        )
        logger.info(
            "De-overreach pass skipped: %s (profile=%s, passes_used=%d/%d).",
            deoverreach_info["skipped_reason"],
            _active_profile,
            _corrective_passes_used,
            _max_corrective_passes,
        )
        _deoverreach_trigger = False
    if _deoverreach_trigger and _latency_budget_exceeded(reserve_s=45.0):
        deoverreach_info["skipped_reason"] = "latency_budget_exhausted"
        logger.info(
            "De-overreach pass skipped: latency budget exhausted "
            "(elapsed=%.1fs, budget=%.1fs).",
            time.monotonic() - _start_ts,
            _latency_budget_s,
        )
        _deoverreach_trigger = False
    if _deoverreach_trigger:
        logger.info(
            "De-overreach rewrite pass triggered "
            "(inference_density=%.2f, unsupported_hr=%d, formula_downgraded=%d, "
            "remaining_passes=%d/%d).",
            current_inference["inference_density"],
            current_claim_risk["unsupported_high_risk_count"],
            current_claim_risk["formula_claims_downgraded_to_concept"],
            _remaining_corrective_passes(),
            _max_corrective_passes,
        )
        with _t("corrective_pass_deoverreach"):
            _dor_text = run_deoverreach_pass(
                final_text, doc_name, citation_anchors, llm_cheap
            )
        if _dor_text and _dor_text.strip() and _dor_text != final_text:
            _dor_text, _ = validate_summary_citations(_dor_text, citation_anchors)
            _dor_text, _dor_grounding = validate_summary_grounding(
                _dor_text, citation_anchors, grounding_threshold
            )
            _dor_claim_risk = classify_claim_risks(_dor_text, citation_anchors)
            _dor_claim_risk = check_formula_mode(
                _dor_claim_risk, citation_anchors, _formula_mode
            )
            _dor_inference = compute_inference_density(_dor_claim_risk)
            if _dor_inference["inference_density"] < current_inference["inference_density"]:
                final_text = _dor_text
                grounding_info = _dor_grounding
                weak_ratio = _compute_weak_ratio(grounding_info)
                used_source_indices = _extract_used_citation_indices(
                    final_text, len(citation_anchors)
                )
                current_claim_risk = _dor_claim_risk
                current_inference = _dor_inference
                deoverreach_info["accepted"] = True
                deoverreach_info["pass_consumed"] = True
                _consume_corrective_pass("deoverreach")
                logger.info(
                    "De-overreach pass accepted: inference_density %.4f → %.4f.",
                    deoverreach_info["inference_density_before"],
                    current_inference["inference_density"],
                )
            else:
                logger.info(
                    "De-overreach pass rejected: density did not improve "
                    "(before=%.4f, candidate=%.4f). Corrective pass not consumed.",
                    deoverreach_info["inference_density_before"],
                    _dor_inference["inference_density"],
                )
        deoverreach_info["inference_density_after"] = current_inference["inference_density"]

    trigger_reasons: list[str] = []
    if (
        grounding_info.get("blocks_with_citations", 0) > 0
        and weak_ratio >= weak_ratio_threshold
    ):
        trigger_reasons.append(
            f"weak-grounding ratio {weak_ratio:.2f} >= {weak_ratio_threshold:.2f}"
        )
    if not structure_info.get("valid", False):
        trigger_reasons.append("structure validation failed")
    if min_unique_sources > 0 and len(used_source_indices) < min_unique_sources:
        trigger_reasons.append(
            f"citation diversity {len(used_source_indices)} < {min_unique_sources}"
        )
    coverage_trigger = (
        coverage_gate_enabled
        and current_coverage["overall_coverage_score"] < coverage_min_score
    )
    if coverage_trigger:
        trigger_reasons.append(
            f"coverage score {current_coverage['overall_coverage_score']:.2f}"
            f" < {coverage_min_score:.2f}"
        )
        logger.warning(
            "Deep summary coverage gate triggered: score=%.2f < threshold=%.2f "
            "(formula=%.2f, procedure=%.2f, example=%.2f, concept=%.2f).",
            current_coverage["overall_coverage_score"],
            coverage_min_score,
            current_coverage["formula_coverage"],
            current_coverage["procedure_coverage"],
            current_coverage["example_coverage"],
            current_coverage["concept_coverage"],
        )
    topic_trigger = (
        topic_gate_enabled
        and bool(current_topic_coverage.get("required_facets"))
        and float(current_topic_coverage.get("overall_score", 1.0)) < topic_min_score
    )
    if topic_trigger:
        trigger_reasons.append(
            f"topic/facet coverage {current_topic_coverage['overall_score']:.2f}"
            f" < {topic_min_score:.2f}"
        )
    # Outline-based topic trigger (stronger: checks explanatory coverage).
    outline_min_score = float(getattr(config, "summary_outline_min_score", 0.60))
    current_outline_must_cover = list(current_outline_coverage.get("must_cover_topics", []))
    current_outline_missing = list(current_outline_coverage.get("missing_topics", []))
    outline_trigger = (
        coverage_gate_enabled
        and bool(current_outline_must_cover)
        and float(current_outline_coverage.get("overall_score", 1.0)) < outline_min_score
        and (
            len(current_outline_must_cover) >= 2
            or bool(current_outline_missing)
        )
    )
    if outline_trigger:
        missing_topics = current_outline_missing
        weakly_covered = current_outline_coverage.get("weakly_covered_topics", [])
        trigger_reasons.append(
            f"outline topic coverage {current_outline_coverage['overall_score']:.2f}"
            f" < {outline_min_score:.2f}"
            f" (missing: {len(missing_topics)}, weak: {len(weakly_covered)})"
        )
    notation_trigger = (
        notation_gate_enabled
        and bool(current_notation.get("active"))
        and float(current_notation.get("score", 1.0)) < notation_min_score
    )
    if notation_trigger:
        trigger_reasons.append(
            f"notation fidelity {current_notation['score']:.2f}"
            f" < {notation_min_score:.2f}"
        )
    claims_trigger = (
        claims_gate_enabled
        and bool(current_critical_claims.get("required_facets"))
        and float(current_critical_claims.get("score", 1.0)) < claims_min_score
    )
    if claims_trigger:
        trigger_reasons.append(
            f"critical-claims coverage {current_critical_claims['score']:.2f}"
            f" < {claims_min_score:.2f}"
        )
    rubric_trigger = (
        rubric_gate_enabled
        and float(current_rubric.get("overall_score", 1.0)) < rubric_min_score
    )
    if rubric_trigger:
        trigger_reasons.append(
            f"rubric score {current_rubric['overall_score']:.2f}"
            f" < {rubric_min_score:.2f}"
        )
    # Inference-density trigger: high-risk claims without solid source support.
    inference_trigger = not current_inference["inference_gate_passed"]
    if inference_trigger:
        trigger_reasons.append(
            f"inference_density {current_inference['inference_density']:.2f}"
            f" > {current_inference['inference_threshold']:.2f}"
        )

    final_structure_info = structure_info
    final_grounding_info = grounding_info
    resynthesis_triggered = bool(resynthesis_enabled and trigger_reasons)
    resynthesis_skipped_reason: str | None = None
    resynthesis_pass_consumed = False
    # Mutual exclusion: if deoverreach was accepted, skip resynthesis for this run.
    if resynthesis_triggered and deoverreach_info.get("accepted"):
        resynthesis_skipped_reason = "deoverreach_accepted_mutual_exclusion"
        logger.info(
            "Deep summary global re-synthesis skipped: de-overreach was accepted "
            "(mutually exclusive corrective passes)."
        )
        resynthesis_triggered = False
    if resynthesis_triggered and _reserve_last_pass_for_must_cover:
        resynthesis_skipped_reason = "reserved_for_must_cover_topics"
        logger.info(
            "Deep summary global re-synthesis skipped: %s (missing must-cover topics=%s, profile=%s).",
            resynthesis_skipped_reason,
            _current_outline_missing,
            _active_profile,
        )
        resynthesis_triggered = False
    if resynthesis_triggered and not _corrective_budget_available():
        resynthesis_skipped_reason = (
            "profile_fast" if _active_profile == "fast" else "corrective_budget_exhausted"
        )
        logger.info(
            "Deep summary global re-synthesis skipped: %s (profile=%s, passes_used=%d/%d).",
            resynthesis_skipped_reason,
            _active_profile,
            _corrective_passes_used,
            _max_corrective_passes,
        )
        resynthesis_triggered = False
    if resynthesis_triggered and _latency_budget_exceeded(reserve_s=30.0):
        resynthesis_skipped_reason = "latency_budget_exhausted"
        logger.info(
            "Deep summary global re-synthesis skipped: latency budget exhausted "
            "(elapsed=%.1fs, budget=%.1fs).",
            time.monotonic() - _start_ts,
            _latency_budget_s,
        )
        resynthesis_triggered = False
    resynthesis_accepted = False
    resynthesis_quality_before: str | None = None
    resynthesis_quality_after: str | None = None
    resynthesis_unique_before: int | None = None
    resynthesis_unique_candidate: int | None = None
    resynthesis_weak_ratio_before: float | None = None
    resynthesis_weak_ratio_candidate: float | None = None
    resynthesis_weak_ratio_delta: float | None = None
    max_weak_ratio_degradation = float(
        getattr(config, "summary_resynthesis_max_weak_ratio_degradation", 0.05)
    )
    # max_accepted_weak_ratio was already defined above (before early backfill)
    # to allow the early backfill ceiling check to use it. Re-use the same value.
    diversity_grounding_guard_blocked = False
    absolute_weak_ratio_blocked = False

    if resynthesis_triggered:
        logger.warning(
            "Deep summary global re-synthesis triggered: %s (remaining_passes=%d/%d).",
            "; ".join(trigger_reasons),
            _remaining_corrective_passes(),
            _max_corrective_passes,
        )
        feedback = _build_resynthesis_feedback(
            structure_info=structure_info,
            grounding_info=grounding_info,
            unique_sources=len(used_source_indices),
            min_unique_sources=min_unique_sources,
            coverage_info=current_coverage if coverage_trigger else None,
            coverage_min_score=coverage_min_score,
            topic_coverage_info=current_topic_coverage if topic_trigger else None,
            topic_coverage_min_score=topic_min_score,
            notation_info=current_notation if notation_trigger else None,
            notation_min_score=notation_min_score,
            critical_claims_info=current_critical_claims if claims_trigger else None,
            critical_claims_min_score=claims_min_score,
        )
        # Add outline-specific feedback when outline trigger fired.
        if outline_trigger:
            outline_missing = current_outline_coverage.get("missing_topics", [])
            outline_weak = current_outline_coverage.get("weakly_covered_topics", [])
            topic_details = topic_info.get("topic_details", {})
            if outline_missing or outline_weak:
                feedback += "\n- TOPIC OUTLINE GAPS:"
                for tid in outline_missing:
                    label = topic_details.get(tid, {}).get("label", tid)
                    feedback += f"\n  - MISSING: {label}"
                for tid in outline_weak:
                    label = topic_details.get(tid, {}).get("label", tid)
                    feedback += f"\n  - WEAK (mentioned but not explained): {label}"
        gap_contract = _build_gap_contract(
            topic_coverage=current_topic_coverage if topic_trigger else None,
            notation_info=current_notation if notation_trigger else None,
            critical_claims=current_critical_claims if claims_trigger else None,
        )
        # Add outline gap contract.
        if outline_trigger:
            outline_missing = current_outline_coverage.get("missing_topics", [])
            outline_weak = current_outline_coverage.get("weakly_covered_topics", [])
            topic_details = topic_info.get("topic_details", {})
            outline_gaps: list[str] = []
            for tid in outline_missing:
                label = topic_details.get(tid, {}).get("label", tid)
                outline_gaps.append(f"- Tópico NÃO coberto: {label}. Explicar em detalhe.")
            for tid in outline_weak:
                label = topic_details.get(tid, {}).get("label", tid)
                outline_gaps.append(f"- Tópico mencionado mas NÃO explicado: {label}. Expandir com conteúdo real.")
            if outline_gaps:
                gap_contract += "\n" + "\n".join(outline_gaps)
        with _t("corrective_pass_resynthesis"):
            candidate_draft = resynthesize_deep_summary(
                draft=final_text,
                consolidated=consolidated,
                partials=partials,
                doc_name=doc_name,
                citation_anchors=citation_anchors,
                quality_feedback=feedback,
                gap_contract=gap_contract,
                min_unique_sources=min_unique_sources,
                llm=llm_complex,
            )
        candidate_text, candidate_info = _postprocess_deep_summary_text(
            candidate_draft,
            citation_anchors,
            grounding_threshold=grounding_threshold,
            llm=llm_cheap,
            repair_enabled=repair_enabled,
            structure_min_chars=structure_min_chars,
        )

        current_unique = len(used_source_indices)
        candidate_unique = len(candidate_info["used_source_indices"])
        resynthesis_unique_before = current_unique
        resynthesis_unique_candidate = candidate_unique
        current_sig = _quality_signature(
            structure_info=structure_info,
            grounding_info=grounding_info,
            unique_sources=current_unique,
            min_unique_sources=min_unique_sources,
        )
        resynthesis_quality_before = str(current_sig)
        candidate_sig = _quality_signature(
            structure_info=candidate_info["structure_info"],
            grounding_info=candidate_info["grounding_info"],
            unique_sources=candidate_unique,
            min_unique_sources=min_unique_sources,
        )

        require_structure = bool(
            getattr(config, "summary_resynthesis_require_structure", True)
        )
        structure_fix_enabled = bool(
            getattr(config, "summary_structure_fix_pass_enabled", True)
        )
        structure_fix_max_calls = int(
            getattr(config, "summary_structure_fix_max_calls", 1)
        )
        candidate_structure_valid = bool(candidate_info["structure_info"].get("valid"))

        # Detect whether diversity was a trigger and candidate improved it.
        diversity_was_trigger = any(
            "citation diversity" in r for r in trigger_reasons
        )
        diversity_improved = candidate_unique > current_unique
        # Structure-fix pass: candidate improves quality but structure is invalid.
        # Triggers when candidate_sig improves OR when diversity improved materially
        # (even if sig didn't improve yet — structure-fix can push it over).
        structure_fix_eligible = (
            candidate_sig > current_sig
            or (diversity_improved and diversity_was_trigger)
        )
        if (
            not candidate_structure_valid
            and require_structure
            and structure_fix_enabled
            and structure_fix_eligible
        ):
            fix_reason = (
                "diversity improved" if diversity_improved and not (candidate_sig > current_sig)
                else "quality improved"
            )
            logger.info(
                "Deep summary: candidate %s (%s → %s, diversity %d → %d) but fails "
                "structure — attempting structure-fix pass (max_calls=%d).",
                fix_reason,
                current_sig,
                candidate_sig,
                current_unique,
                candidate_unique,
                structure_fix_max_calls,
            )
            for _fix_n in range(max(1, structure_fix_max_calls)):
                fixed_draft = _apply_structure_fix(candidate_text, doc_name, llm_complex)
                fixed_text, fixed_info = _postprocess_deep_summary_text(
                    fixed_draft,
                    citation_anchors,
                    grounding_threshold=grounding_threshold,
                    llm=llm_cheap,
                    repair_enabled=repair_enabled,
                    structure_min_chars=structure_min_chars,
                )
                if bool(fixed_info["structure_info"].get("valid")):
                    candidate_text = fixed_text
                    candidate_info = fixed_info
                    candidate_unique = len(candidate_info["used_source_indices"])
                    candidate_sig = _quality_signature(
                        structure_info=candidate_info["structure_info"],
                        grounding_info=candidate_info["grounding_info"],
                        unique_sources=candidate_unique,
                        min_unique_sources=min_unique_sources,
                    )
                    candidate_structure_valid = True
                    logger.info(
                        "Deep summary structure-fix: succeeded (attempt %d/%d).",
                        _fix_n + 1,
                        structure_fix_max_calls,
                    )
                    break
                logger.info(
                    "Deep summary structure-fix: attempt %d/%d — structure still invalid.",
                    _fix_n + 1,
                    structure_fix_max_calls,
                )

        # Coverage acceptance: when coverage was the (or a) trigger, check whether
        # the candidate reaches or improves coverage relative to the current text.
        candidate_coverage = score_coverage(
            candidate_text,
            coverage_signals,
            coverage_profile=coverage_profile,
        )
        if coverage_trigger:
            candidate_cov_score = candidate_coverage["overall_coverage_score"]
            coverage_gain = candidate_cov_score >= coverage_min_score
            logger.info(
                "Deep summary coverage gate: candidate score=%.2f (threshold=%.2f) — %s.",
                candidate_cov_score,
                coverage_min_score,
                "meets threshold" if coverage_gain else "still below threshold",
            )
        else:
            coverage_gain = False

        candidate_topic_coverage = score_topic_coverage(candidate_text, doc_profile)
        candidate_outline_coverage = score_topic_outline_coverage(candidate_text, topic_info)
        candidate_notation = assess_notation_fidelity(candidate_text, doc_profile)
        candidate_critical_claims = evaluate_critical_claim_coverage(
            candidate_text,
            doc_profile,
        )
        candidate_rubric = compute_summary_rubric(
            structure_valid=bool(candidate_info["structure_info"].get("valid")),
            weak_ratio=_compute_weak_ratio(candidate_info["grounding_info"]),
            unique_sources=candidate_unique,
            min_unique_sources=min_unique_sources,
            coverage_score=float(candidate_coverage.get("overall_coverage_score", 1.0)),
            facet_score=float(candidate_topic_coverage.get("overall_score", 1.0)),
            claims_score=float(candidate_critical_claims.get("score", 1.0)),
            notation_score=float(candidate_notation.get("score", 1.0)),
            outline_score=float(candidate_outline_coverage.get("overall_score", 1.0)),
        )
        topic_gain = (
            not topic_trigger
            or float(candidate_topic_coverage.get("overall_score", 1.0)) >= topic_min_score
        )
        outline_gain = (
            not outline_trigger
            or float(candidate_outline_coverage.get("overall_score", 1.0)) >= outline_min_score
        )
        notation_gain = (
            not notation_trigger
            or float(candidate_notation.get("score", 1.0)) >= notation_min_score
        )
        claims_gain = (
            not claims_trigger
            or float(candidate_critical_claims.get("score", 1.0)) >= claims_min_score
        )
        rubric_gain = (
            not rubric_trigger
            or float(candidate_rubric.get("overall_score", 1.0)) >= rubric_min_score
        )

        # Guardrail: when diversity improved due diversity-triggered re-synthesis,
        # don't accept candidates that degrade grounding too much.
        current_weak_ratio = _compute_weak_ratio(grounding_info)
        candidate_weak_ratio = _compute_weak_ratio(candidate_info["grounding_info"])
        weak_ratio_delta = candidate_weak_ratio - current_weak_ratio
        resynthesis_weak_ratio_before = round(current_weak_ratio, 4)
        resynthesis_weak_ratio_candidate = round(candidate_weak_ratio, 4)
        resynthesis_weak_ratio_delta = round(weak_ratio_delta, 4)
        diversity_grounding_guard_passed = True
        if diversity_was_trigger and diversity_improved:
            diversity_grounding_guard_passed = weak_ratio_delta <= max_weak_ratio_degradation
            if not diversity_grounding_guard_passed:
                diversity_grounding_guard_blocked = True
                logger.warning(
                    "Deep summary re-synthesis guard: diversity improved (%d → %d) but "
                    "grounding degraded too much (weak_ratio %.2f → %.2f, delta=%.2f > max=%.2f).",
                    current_unique,
                    candidate_unique,
                    current_weak_ratio,
                    candidate_weak_ratio,
                    weak_ratio_delta,
                    max_weak_ratio_degradation,
                )

        # Absolute ceiling: reject candidate outright if weak_ratio is too high.
        if candidate_weak_ratio > max_accepted_weak_ratio:
            absolute_weak_ratio_blocked = True
            logger.warning(
                "Deep summary re-synthesis guard: candidate weak_ratio %.2f exceeds "
                "absolute ceiling %.2f — rejecting regardless of other gains.",
                candidate_weak_ratio,
                max_accepted_weak_ratio,
            )

        hard_gain = (
            bool(candidate_info["structure_info"].get("valid"))
            or (candidate_unique >= min_unique_sources > 0)
            or (candidate_unique > current_unique)
            or (coverage_trigger and coverage_gain)
            or (topic_trigger and topic_gain)
            or (outline_trigger and outline_gain)
            or (notation_trigger and notation_gain)
            or (claims_trigger and claims_gain)
            or (rubric_trigger and rubric_gain)
        )
        if require_structure and not candidate_structure_valid:
            # Recovery rule: if the ONLY failure reason is section_count_exceeded,
            # attempt deterministic auto-merge and revalidate.
            failure_reason = candidate_info["structure_info"].get("structure_failure_reason", "")
            if failure_reason == "section_count_exceeded" and hard_gain:
                logger.info(
                    "Deep summary recovery: candidate fails only on section_count_exceeded "
                    "— attempting auto-merge (diversity %d → %d).",
                    current_unique,
                    candidate_unique,
                )
                recovered_text, recovery_merge_info = _auto_merge_sections(candidate_text, target_sections=5)
                if recovery_merge_info.get("merges_applied"):
                    recovered_text = _sanitize_inline_source_noise(recovered_text)
                    recovered_text, _ = validate_summary_citations(recovered_text, citation_anchors)
                    recovered_structure = validate_summary_structure(
                        recovered_text,
                        min_section_chars=structure_min_chars,
                    )
                    if recovered_structure.get("valid"):
                        candidate_text = recovered_text
                        candidate_info["structure_info"] = recovered_structure
                        candidate_info["auto_merge_applied"] = True
                        candidate_info["merge_info"] = recovery_merge_info
                        candidate_unique = len(
                            _extract_used_citation_indices(recovered_text, len(citation_anchors))
                        )
                        candidate_info["used_source_indices"] = _extract_used_citation_indices(
                            recovered_text, len(citation_anchors)
                        )
                        candidate_sig = _quality_signature(
                            structure_info=recovered_structure,
                            grounding_info=candidate_info["grounding_info"],
                            unique_sources=candidate_unique,
                            min_unique_sources=min_unique_sources,
                        )
                        candidate_structure_valid = True
                        logger.info(
                            "Deep summary recovery: auto-merge succeeded (%d → %d sections), "
                            "candidate now valid.",
                            recovery_merge_info["section_count_before"],
                            recovery_merge_info["section_count_after"],
                        )

            # If still invalid after recovery attempt, discard.
            if not candidate_structure_valid:
                logger.info(
                    "Deep summary global re-synthesis discarded — structure invalid "
                    "after %s (sig current=%s, candidate=%s, diversity %d → %d).",
                    f"structure-fix attempt (max={structure_fix_max_calls})"
                    if structure_fix_enabled
                    else "no fix attempt",
                    current_sig,
                    candidate_sig,
                    current_unique,
                    candidate_unique,
                )
                resynthesis_quality_after = str(current_sig)
        elif absolute_weak_ratio_blocked:
            logger.info(
                "Deep summary global re-synthesis discarded — candidate weak_ratio %.2f "
                "exceeds absolute ceiling %.2f.",
                candidate_weak_ratio,
                max_accepted_weak_ratio,
            )
            resynthesis_quality_after = str(current_sig)
        elif candidate_sig > current_sig and hard_gain and diversity_grounding_guard_passed:
            logger.info(
                "Deep summary global re-synthesis accepted (quality %s → %s, "
                "diversity %d → %d).",
                current_sig,
                candidate_sig,
                current_unique,
                candidate_unique,
            )
            final_text = candidate_text
            used_source_indices = list(candidate_info["used_source_indices"])
            final_structure_info = candidate_info["structure_info"]
            final_grounding_info = candidate_info["grounding_info"]
            dropped_weak_sections = int(candidate_info.get("dropped_weak_sections", dropped_weak_sections))
            resynthesis_accepted = True
            resynthesis_pass_consumed = True
            _consume_corrective_pass("resynthesis")
            resynthesis_quality_after = str(candidate_sig)
        elif (
            diversity_was_trigger
            and diversity_improved
            and candidate_structure_valid
            and hard_gain
            and diversity_grounding_guard_passed
        ):
            # Diversity-driven acceptance: candidate has valid structure and
            # materially better diversity, even if overall quality signature
            # didn't strictly improve (e.g. grounding slightly worse).
            logger.info(
                "Deep summary global re-synthesis accepted via diversity gain "
                "(diversity %d → %d, structure valid, sig %s → %s).",
                current_unique,
                candidate_unique,
                current_sig,
                candidate_sig,
            )
            final_text = candidate_text
            used_source_indices = list(candidate_info["used_source_indices"])
            final_structure_info = candidate_info["structure_info"]
            final_grounding_info = candidate_info["grounding_info"]
            dropped_weak_sections = int(candidate_info.get("dropped_weak_sections", dropped_weak_sections))
            resynthesis_accepted = True
            resynthesis_pass_consumed = True
            _consume_corrective_pass("resynthesis")
            resynthesis_quality_after = str(candidate_sig)
        elif diversity_grounding_guard_blocked:
            logger.info(
                "Deep summary global re-synthesis discarded — diversity gain blocked by "
                "grounding degradation guard (weak_ratio %.2f → %.2f, delta=%.2f > max=%.2f).",
                current_weak_ratio,
                candidate_weak_ratio,
                weak_ratio_delta,
                max_weak_ratio_degradation,
            )
            resynthesis_quality_after = str(current_sig)
        else:
            logger.info(
                "Deep summary global re-synthesis discarded (quality %s ≤ %s, "
                "diversity %d → %d, no hard gain).",
                candidate_sig,
                current_sig,
                current_unique,
                candidate_unique,
            )
            resynthesis_quality_after = str(current_sig)
        if not resynthesis_pass_consumed:
            logger.info(
                "Deep summary global re-synthesis: corrective pass not consumed "
                "(candidate not accepted)."
            )

    # Hard cleanup pass right before appending authoritative sources. This is a
    # final guardrail against leaked source dumps (e.g. "Fonte 9", "[Fonte N] ...pdf")
    # and non-canonical brackets (e.g. "[Contexto adicional, p. 4]").
    final_text = _strip_sources_section(final_text)
    final_text = _sanitize_inline_source_noise(final_text)
    final_text = _sanitize_non_canonical_citations(final_text)
    final_text = _sanitize_before_structure_validation(final_text)
    final_text, final_citation_cleanup = validate_summary_citations(
        final_text,
        citation_anchors,
    )
    if final_citation_cleanup.get("repaired"):
        logger.warning(
            "Deep summary final cleanup: removed %d phantom citation(s).",
            len(final_citation_cleanup.get("phantom_indices", [])),
        )
    used_source_indices = _extract_used_citation_indices(final_text, len(citation_anchors))

    # ── Topic backfill step (micro-backfill, post-resynthesis) ───────────────
    # If outline coverage still has missing topics after resynthesis/deoverreach,
    # attempt a micro-backfill as a second opportunity. When backfill-before-
    # deoverreach already ran and resolved all topics, this step naturally becomes
    # a no-op (backfill_missing will be empty). When it did not fully resolve
    # them, this step catches the remainder (budget permitting).
    _micro_backfill_enabled = bool(getattr(config, "summary_micro_backfill_enabled", True))
    _micro_backfill_max_topics = int(getattr(config, "summary_micro_backfill_max_topics", 3))
    _micro_backfill_para_max = int(getattr(config, "summary_micro_backfill_paragraph_max_chars", 900))
    backfill_info: dict[str, Any] = {
        "triggered": False,
        "accepted": False,
        "missing_before": [],
        "missing_after": [],
        "rollback_reason": None,
        "absolute_weak_ratio_blocked": False,
        "weak_ratio_before": round(_compute_weak_ratio(final_grounding_info), 4),
        "weak_ratio_after": None,
        # micro-backfill specific
        "paragraphs_attempted": 0,
        "paragraphs_accepted": 0,
        "latency_ms": 0.0,
        "skipped_topics": [],
    }
    pre_backfill_outline = score_topic_outline_coverage(final_text, topic_info)
    backfill_missing = list(pre_backfill_outline.get("missing_topics", []))
    if (
        backfill_missing
        and topic_info.get("must_cover_topics")
        and _corrective_budget_available()
        and not _latency_budget_exceeded(reserve_s=20.0)
        and _micro_backfill_enabled
    ):
        _consume_corrective_pass("micro_backfill")
        backfill_info["triggered"] = True
        backfill_info["missing_before"] = list(backfill_missing)
        logger.info(
            "Deep summary micro-backfill triggered: %d missing topic(s): %s "
            "(corrective_pass=%d/%d, max_topics=%d).",
            len(backfill_missing),
            backfill_missing,
            _corrective_passes_used,
            _max_corrective_passes,
            _micro_backfill_max_topics,
        )
        try:
            with _t("micro_backfill"):
                _micro_result = _run_micro_topic_backfill(
                    final_text=final_text,
                    missing_topics=backfill_missing,
                    topic_info=topic_info,
                    all_chunks=chunks,
                    citation_anchors=citation_anchors,
                    doc_name=doc_name,
                    llm=llm_cheap,
                    max_topics=_micro_backfill_max_topics,
                    paragraph_max_chars=_micro_backfill_para_max,
                )

            backfill_info["paragraphs_attempted"] = _micro_result["paragraphs_attempted"]
            backfill_info["paragraphs_accepted"] = _micro_result["paragraphs_accepted"]
            backfill_info["missing_after"] = _micro_result["missing_topics_after"]
            backfill_info["latency_ms"] = _micro_result["latency_ms"]
            backfill_info["skipped_topics"] = _micro_result.get("skipped_topics", [])

            if _micro_result["paragraphs_accepted"] > 0:
                new_text = _micro_result["text"]
                # Validate the enriched text: citations + grounding.
                new_text = _sanitize_non_canonical_citations(new_text)
                new_text, _ = validate_summary_citations(new_text, citation_anchors)
                new_text, bf_grounding = validate_summary_grounding(
                    new_text, citation_anchors, grounding_threshold
                )
                bf_weak_ratio = _compute_weak_ratio(bf_grounding)
                backfill_info["weak_ratio_after"] = round(bf_weak_ratio, 4)
                absolute_ceiling_exceeded = bf_weak_ratio > max_accepted_weak_ratio

                if absolute_ceiling_exceeded:
                    backfill_info["rollback_reason"] = "absolute_weak_ratio_exceeded"
                    backfill_info["absolute_weak_ratio_blocked"] = True
                    logger.warning(
                        "Deep summary micro-backfill rejected: absolute weak_ratio ceiling exceeded "
                        "(bf_weak_ratio=%.2f > ceiling=%.2f). Discarding micro-backfill.",
                        bf_weak_ratio,
                        max_accepted_weak_ratio,
                    )
                else:
                    final_text = new_text
                    final_grounding_info = bf_grounding
                    used_source_indices = _extract_used_citation_indices(final_text, len(citation_anchors))
                    backfill_info["accepted"] = True
                    logger.info(
                        "Deep summary micro-backfill accepted: %d/%d paragraph(s) accepted, "
                        "missing topics %d → %d, weak_ratio %.2f → %.2f.",
                        _micro_result["paragraphs_accepted"],
                        _micro_result["paragraphs_attempted"],
                        len(backfill_missing),
                        len(_micro_result["missing_topics_after"]),
                        backfill_info["weak_ratio_before"],
                        bf_weak_ratio,
                    )
            else:
                backfill_info["rollback_reason"] = "no_paragraphs_accepted"
                logger.info(
                    "Deep summary micro-backfill: no paragraphs accepted (0/%d attempted).",
                    _micro_result["paragraphs_attempted"],
                )
        except Exception as exc:
            backfill_info["rollback_reason"] = f"error: {exc}"
            logger.warning("Deep summary micro-backfill failed: %s.", exc)
    elif backfill_missing and topic_info.get("must_cover_topics"):
        if not _corrective_budget_available():
            backfill_info["rollback_reason"] = (
                "profile_fast" if _active_profile == "fast" else "corrective_budget_exhausted"
            )
            logger.info(
                "Deep summary topic backfill skipped: %s (profile=%s, passes_used=%d/%d).",
                backfill_info["rollback_reason"],
                _active_profile,
                _corrective_passes_used,
                _max_corrective_passes,
            )
        elif not _micro_backfill_enabled:
            backfill_info["rollback_reason"] = "micro_backfill_disabled"
            logger.info("Deep summary topic backfill skipped: micro_backfill disabled.")
        else:
            backfill_info["rollback_reason"] = "latency_budget_exhausted"
            logger.info(
                "Deep summary topic backfill skipped: latency budget exhausted "
                "(elapsed=%.1fs, budget=%.1fs).",
                time.monotonic() - _start_ts,
                _latency_budget_s,
            )

    # Final canonical-citation guardrail: runs unconditionally after the backfill
    # step (whether backfill was triggered or not) to ensure the answer never
    # contains non-canonical bracket citations such as [Contexto adicional, p. 4].
    final_text = _sanitize_non_canonical_citations(final_text)
    final_text, _post_backfill_cleanup = validate_summary_citations(final_text, citation_anchors)
    used_source_indices = _extract_used_citation_indices(final_text, len(citation_anchors))

    # ── Absolute weak-ratio hard gate (post-backfill) ─────────────────────────
    # Recalculate final_weak_ratio now so the gate uses the current grounding
    # info (which may have been updated by backfill acceptance).
    final_weak_ratio = _compute_weak_ratio(final_grounding_info)
    final_absolute_weak_ratio_passed: bool = True

    if final_weak_ratio > max_accepted_weak_ratio:
        logger.warning(
            "Deep summary post-backfill: final weak_ratio=%.2f exceeds absolute ceiling=%.2f. "
            "Attempting grounding repair.",
            final_weak_ratio,
            max_accepted_weak_ratio,
        )
        # Try one last grounding repair pass when repair is enabled.
        if repair_enabled and not _latency_budget_exceeded(reserve_s=10.0):
            final_text, final_grounding_info = validate_summary_grounding(
                final_text,
                citation_anchors,
                grounding_threshold,
                llm=llm_cheap,
            )
            final_weak_ratio = _compute_weak_ratio(final_grounding_info)

        if final_weak_ratio > max_accepted_weak_ratio:
            final_absolute_weak_ratio_passed = False
            logger.warning(
                "Deep summary final gate: weak_ratio=%.2f still exceeds absolute ceiling=%.2f "
                "after repair attempt. Marking as quality warning in diagnostics.",
                final_weak_ratio,
                max_accepted_weak_ratio,
            )
        else:
            logger.info(
                "Deep summary final gate: grounding repair reduced weak_ratio to %.2f "
                "(ceiling=%.2f). Gate passed.",
                final_weak_ratio,
                max_accepted_weak_ratio,
            )

    final_structure_info = validate_summary_structure(
        final_text,
        min_section_chars=structure_min_chars,
    )

    final_coverage: dict[str, Any] = score_coverage(
        final_text,
        coverage_signals,
        coverage_profile=coverage_profile,
    )
    # final_weak_ratio already computed by the absolute weak-ratio gate above;
    # recalculate here to pick up any repair that happened inside that gate.
    final_weak_ratio = _compute_weak_ratio(final_grounding_info)
    final_topic_coverage = score_topic_coverage(final_text, doc_profile)
    final_outline_coverage = score_topic_outline_coverage(final_text, topic_info)

    # ── Final claim-risk / inference-density snapshot (post-resynthesis/backfill) ──
    # Recompute on the current final_text so diagnostics reflect post-repair state.
    final_claim_risk = classify_claim_risks(final_text, citation_anchors)
    final_claim_risk = check_formula_mode(
        final_claim_risk, citation_anchors, _formula_mode
    )
    final_inference = compute_inference_density(final_claim_risk)
    _unsupported_high_risk_sentences: list[dict[str, Any]] = []
    for _idx, _sent in enumerate(final_claim_risk.get("sentences_classified", [])):
        if not (_sent.get("high_risk") and _sent.get("unsupported")):
            continue
        _text = str(_sent.get("text", "")).strip()
        if len(_text) > 260:
            _text = _text[:257] + "..."
        _unsupported_high_risk_sentences.append(
            {
                "index": int(_idx),
                "risk_type": str(_sent.get("risk_type", "unknown")),
                "low_info_only": bool(_sent.get("low_info_only", False)),
                "cited_sources": [
                    f"Fonte {int(i) + 1}" for i in (_sent.get("cited_indices") or [])
                ],
                "text": _text,
            }
        )
    _unsupported_high_risk_sentences = _unsupported_high_risk_sentences[:8]

    # ── Extra outline-repair pass ─────────────────────────────────────────────
    # If must_cover_topics are defined and some are still missing after backfill,
    # attempt one more micro-backfill pass focused exclusively on those topics.
    # This stays bounded (no global rewrite): we only accept if structure is OK,
    # grounding is within guardrails, and at least one missing topic is resolved.
    _extra_backfill_info: dict[str, Any] = {"triggered": False, "accepted": False, "missing_after": []}
    _final_missing = list(final_outline_coverage.get("missing_topics", []))
    _must_cover = list(final_outline_coverage.get("must_cover_topics", []))
    if (
        _final_missing
        and _must_cover
        and _corrective_budget_available()
        and not _latency_budget_exceeded(reserve_s=5.0)
    ):
        _consume_corrective_pass("micro_backfill_extra_outline")
        logger.info(
            "Deep summary extra outline-repair micro-pass: %d missing must-cover topic(s): %s "
            "(corrective_pass=%d/%d).",
            len(_final_missing),
            _final_missing,
            _corrective_passes_used,
            _max_corrective_passes,
        )
        _extra_backfill_info["triggered"] = True
        try:
            with _t("micro_backfill_extra_outline"):
                _extra_micro = _run_micro_topic_backfill(
                    final_text=final_text,
                    missing_topics=_final_missing,
                    topic_info=topic_info,
                    all_chunks=chunks,
                    citation_anchors=citation_anchors,
                    doc_name=doc_name,
                    llm=llm_cheap,
                    max_topics=_micro_backfill_max_topics,
                    paragraph_max_chars=_micro_backfill_para_max,
                )
            _extra_backfill_info["paragraphs_attempted"] = int(
                _extra_micro.get("paragraphs_attempted", 0)
            )
            _extra_backfill_info["paragraphs_accepted"] = int(
                _extra_micro.get("paragraphs_accepted", 0)
            )
            _extra_backfill_info["latency_ms"] = float(_extra_micro.get("latency_ms", 0.0))
            _extra_backfill_info["missing_before"] = list(_final_missing)

            _extra_bf_text_raw = str(_extra_micro.get("text") or "").strip()
            if _extra_bf_text_raw:
                _ebf = _strip_sources_section(_extra_bf_text_raw)
                _ebf = _sanitize_inline_source_noise(_ebf)
                _ebf = _sanitize_non_canonical_citations(_ebf)
                _ebf = _sanitize_before_structure_validation(_ebf)
                _ebf, _ = validate_summary_citations(_ebf, citation_anchors)
                _ebf_structure = validate_summary_structure(_ebf, min_section_chars=structure_min_chars)
                _ebf, _ebf_grounding = validate_summary_grounding(
                    _ebf,
                    citation_anchors,
                    grounding_threshold,
                    llm=llm_cheap if repair_enabled else None,
                )
                _ebf_weak_ratio = _compute_weak_ratio(_ebf_grounding)
                _ebf_outline = score_topic_outline_coverage(_ebf, topic_info)
                _ebf_missing = list(_ebf_outline.get("missing_topics", []))
                _extra_backfill_info["missing_after"] = list(_ebf_missing)

                _ebf_structure_ok = not _is_structure_degraded(
                    validate_summary_structure(final_text, min_section_chars=structure_min_chars),
                    _ebf_structure,
                )
                _ebf_grounding_ok = _ebf_weak_ratio <= (
                    _compute_weak_ratio(final_grounding_info) + max_weak_ratio_degradation
                ) and _ebf_weak_ratio <= max_accepted_weak_ratio
                _ebf_improved = len(_ebf_missing) < len(_final_missing)

                if _ebf_structure_ok and _ebf_grounding_ok and _ebf_improved:
                    final_text = _ebf
                    final_grounding_info = _ebf_grounding
                    final_weak_ratio = _ebf_weak_ratio
                    used_source_indices = _extract_used_citation_indices(final_text, len(citation_anchors))
                    _extra_backfill_info["accepted"] = True
                    # Recompute outline coverage with the repaired text.
                    final_outline_coverage = _ebf_outline
                    logger.info(
                        "Deep summary extra outline-repair accepted: missing topics %d → %d "
                        "(paragraphs=%d/%d).",
                        len(_final_missing),
                        len(_ebf_missing),
                        _extra_backfill_info["paragraphs_accepted"],
                        _extra_backfill_info["paragraphs_attempted"],
                    )
                else:
                    logger.info(
                        "Deep summary extra outline-repair rolled back "
                        "(structure_ok=%s, grounding_ok=%s, improved=%s).",
                        _ebf_structure_ok,
                        _ebf_grounding_ok,
                        _ebf_improved,
                    )
            else:
                logger.info(
                    "Deep summary extra outline-repair micro-pass: no candidate text generated "
                    "(paragraphs=%d/%d).",
                    _extra_backfill_info["paragraphs_accepted"],
                    _extra_backfill_info["paragraphs_attempted"],
                )
        except Exception as _ebf_exc:
            logger.warning("Deep summary extra outline-repair failed: %s.", _ebf_exc)
    elif _final_missing and _must_cover:
        if not _corrective_budget_available():
            _skip_reason = (
                "profile_fast" if _active_profile == "fast" else "corrective_budget_exhausted"
            )
            logger.info(
                "Deep summary extra outline-repair skipped: %s "
                "(profile=%s, passes_used=%d/%d).",
                _skip_reason,
                _active_profile,
                _corrective_passes_used,
                _max_corrective_passes,
            )
        else:
            logger.info(
                "Deep summary extra outline-repair skipped: latency budget exhausted "
                "(elapsed=%.1fs, budget=%.1fs).",
                time.monotonic() - _start_ts,
                _latency_budget_s,
            )

    # If extra outline-repair changed final_text, refresh all downstream metrics.
    # Without this refresh, diagnostics/final gates could reflect stale state.
    if _extra_backfill_info.get("accepted"):
        final_structure_info = validate_summary_structure(
            final_text,
            min_section_chars=structure_min_chars,
        )
        final_coverage = score_coverage(
            final_text,
            coverage_signals,
            coverage_profile=coverage_profile,
        )
        final_weak_ratio = _compute_weak_ratio(final_grounding_info)
        final_topic_coverage = score_topic_coverage(final_text, doc_profile)
        final_outline_coverage = score_topic_outline_coverage(final_text, topic_info)
        final_claim_risk = classify_claim_risks(final_text, citation_anchors)
        final_claim_risk = check_formula_mode(
            final_claim_risk, citation_anchors, _formula_mode
        )
        final_inference = compute_inference_density(final_claim_risk)

    final_notation = assess_notation_fidelity(final_text, doc_profile)
    final_critical_claims = evaluate_critical_claim_coverage(final_text, doc_profile)
    final_rubric = compute_summary_rubric(
        structure_valid=bool(final_structure_info.get("valid", False)),
        weak_ratio=final_weak_ratio,
        unique_sources=len(used_source_indices),
        min_unique_sources=min_unique_sources,
        coverage_score=float(final_coverage.get("overall_coverage_score", 1.0)),
        facet_score=float(final_topic_coverage.get("overall_score", 1.0)),
        claims_score=float(final_critical_claims.get("score", 1.0)),
        notation_score=float(final_notation.get("score", 1.0)),
        outline_score=float(final_outline_coverage.get("overall_score", 1.0)),
    )
    logger.info(
        "Deep summary sources: %d/%d anchor(s) cited in final text.",
        len(used_source_indices),
        len(citation_anchors),
    )
    if min_unique_sources > 0 and len(used_source_indices) < min_unique_sources:
        logger.warning(
            "Deep summary citation diversity below target: %d < %d unique sources.",
            len(used_source_indices),
            min_unique_sources,
        )
    sources_section = build_anchor_sources_section(
        citation_anchors,
        source_indices=used_source_indices,
    )
    if sources_section:
        final_text = final_text.rstrip() + "\n\n" + sources_section

    final_absolute_weak_ratio_passed = final_weak_ratio <= max_accepted_weak_ratio

    diagnostics = {
        "coverage": {
            "overall_coverage_score": final_coverage.get("overall_coverage_score", 1.0),
            "formula_coverage": final_coverage.get("formula_coverage", 1.0),
            "procedure_coverage": final_coverage.get("procedure_coverage", 1.0),
            "example_coverage": final_coverage.get("example_coverage", 1.0),
            "concept_coverage": final_coverage.get("concept_coverage", 1.0),
            "gate_enabled": coverage_gate_enabled,
            "min_score": coverage_min_score,
        },
        "coverage_signals": {
            "formula_chunks": int(coverage_signals.get("formula_chunks", 0)),
            "procedure_chunks": int(coverage_signals.get("procedure_chunks", 0)),
            "example_chunks": int(coverage_signals.get("example_chunks", 0)),
            "concept_chunks": int(coverage_signals.get("concept_chunks", 0)),
            "total_chunks": int(coverage_signals.get("total_chunks", len(chunks))),
        },
        "coverage_profile": {
            "name": str(coverage_profile.get("name", "balanced")),
            "reason": str(coverage_profile.get("reason", "")),
        },
        "document_profile": {
            "required_facets": list(doc_profile.get("required_facets", [])),
            "critical_required_facets": list(doc_profile.get("critical_required_facets", [])),
            "pdf_outline_sections": len(pdf_outline_entries),
            "facet_hits": {
                facet: int((doc_profile.get("facets", {}).get(facet, {}) or {}).get("hits", 0))
                for facet in _FACET_ORDER
            },
            "notation": {
                "cardinality_vars": list((doc_profile.get("notation", {}) or {}).get("cardinality_vars", [])),
                "greek_symbols": list((doc_profile.get("notation", {}) or {}).get("greek_symbols", [])),
                "formula_lines": int((doc_profile.get("notation", {}) or {}).get("formula_lines", 0)),
            },
        },
        "topic_coverage": {
            "score": float(final_topic_coverage.get("overall_score", 1.0)),
            "required_facets": list(final_topic_coverage.get("required_facets", [])),
            "covered_facets": list(final_topic_coverage.get("covered_facets", [])),
            "missing_facets": list(final_topic_coverage.get("missing_facets", [])),
            "gate_enabled": topic_gate_enabled,
            "min_score": topic_min_score,
        },
        "outline_coverage": {
            "score": float(final_outline_coverage.get("overall_score", 1.0)),
            "detected_topics": list(final_outline_coverage.get("detected_topics", [])),
            "must_cover_topics": list(final_outline_coverage.get("must_cover_topics", [])),
            "covered_topics": list(final_outline_coverage.get("covered_topics", [])),
            "missing_topics": list(final_outline_coverage.get("missing_topics", [])),
            "weakly_covered_topics": list(final_outline_coverage.get("weakly_covered_topics", [])),
            "topic_scores": dict(final_outline_coverage.get("topic_scores", {})),
            "gate_enabled": coverage_gate_enabled,
            "min_score": outline_min_score,
        },
        "notation_fidelity": {
            "score": float(final_notation.get("score", 1.0)),
            "active": bool(final_notation.get("active", False)),
            "issues": list(final_notation.get("issues", [])),
            "missing_legends": list(final_notation.get("missing_legends", [])),
            "checked_vars": list(final_notation.get("checked_vars", [])),
            "legend_required": bool(final_notation.get("legend_required", False)),
            "gate_enabled": notation_gate_enabled,
            "min_score": notation_min_score,
        },
        "critical_claims": {
            "score": float(final_critical_claims.get("score", 1.0)),
            "required_facets": list(final_critical_claims.get("required_facets", [])),
            "supported_facets": list(final_critical_claims.get("supported_facets", [])),
            "missing_facets": list(final_critical_claims.get("missing_facets", [])),
            "gate_enabled": claims_gate_enabled,
            "min_score": claims_min_score,
            "local_repair": dict(claim_local_repair_info),
        },
        "rubric": {
            **final_rubric,
            "gate_enabled": rubric_gate_enabled,
            "min_score": rubric_min_score,
        },
        "structure": {
            "valid": bool(final_structure_info.get("valid", False)),
            "required_sections_ok": not bool(final_structure_info.get("missing_categories", [])),
            "missing_sections": list(final_structure_info.get("missing_categories", [])),
            "missing_heading_sections": list(final_structure_info.get("missing_heading_categories", [])),
            "body_fallback_categories": list(final_structure_info.get("body_fallback_categories", [])),
            "weak_sections_dropped": dropped_weak_sections,
            "section_count": int(final_structure_info.get("section_count", 0)),
            "closure_section_ok": bool(final_structure_info.get("closure_section_ok", False)),
            "structure_failure_reason": str(final_structure_info.get("structure_failure_reason", "")),
            "auto_merge_applied": bool(structure_pass.get("auto_merge_applied", False)),
            "section_count_before": int(
                structure_pass.get("merge_info", {}).get("section_count_before", 0)
            ) if structure_pass.get("auto_merge_applied") else None,
            "section_count_after": int(
                structure_pass.get("merge_info", {}).get("section_count_after", 0)
            ) if structure_pass.get("auto_merge_applied") else None,
        },
        "grounding": {
            "threshold": grounding_threshold,
            "blocks_with_citations": int(final_grounding_info.get("blocks_with_citations", 0)),
            "weakly_grounded": int(final_grounding_info.get("weakly_grounded", 0)),
            "repaired_blocks": int(final_grounding_info.get("repaired_blocks", 0)),
            "weak_ratio": round(final_weak_ratio, 4),
        },
        "citations": {
            "anchors_total": len(citation_anchors),
            "unique_sources_used": len(used_source_indices),
            "min_unique_sources": min_unique_sources,
            "min_unique_sources_config": min_unique_sources_cfg,
            "adaptive_reason": (
                f"cap=min(config={min_unique_sources_cfg}, "
                f"anchors_50pct={-(-n_anchors // 2) if n_anchors > 0 else 0}, "
                f"groups={n_groups})"
            ),
        },
        "resynthesis": {
            "enabled": resynthesis_enabled,
            "triggered": resynthesis_triggered,
            "pass_consumed": bool(resynthesis_pass_consumed),
            "skipped_reason": resynthesis_skipped_reason,
            "trigger_reasons": list(trigger_reasons),
            "topic_triggered": bool(topic_trigger),
            "outline_triggered": bool(outline_trigger),
            "notation_triggered": bool(notation_trigger),
            "critical_claims_triggered": bool(claims_trigger),
            "rubric_triggered": bool(rubric_trigger),
            "inference_triggered": bool(inference_trigger),
            "diversity_was_primary_trigger": any(
                "citation diversity" in r for r in trigger_reasons
            ),
            "accepted": resynthesis_accepted,
            "quality_before": resynthesis_quality_before,
            "quality_after": resynthesis_quality_after,
            "unique_sources_before": resynthesis_unique_before,
            "unique_sources_candidate": resynthesis_unique_candidate,
            "grounding_weak_ratio_before": resynthesis_weak_ratio_before,
            "grounding_weak_ratio_candidate": resynthesis_weak_ratio_candidate,
            "grounding_weak_ratio_delta": resynthesis_weak_ratio_delta,
            "max_allowed_weak_ratio_degradation": round(max_weak_ratio_degradation, 4),
            "max_accepted_weak_ratio": round(max_accepted_weak_ratio, 4),
            "absolute_weak_ratio_blocked": absolute_weak_ratio_blocked,
            "diversity_grounding_guard_blocked": diversity_grounding_guard_blocked,
        },
        "backfill": backfill_info,
        "extra_outline_repair": _extra_backfill_info,
        "claim_risk": {
            "sentences_total": int(final_claim_risk.get("sentences_total", 0)),
            "high_risk_count": int(final_claim_risk.get("high_risk_count", 0)),
            "unsupported_high_risk_count": int(
                final_claim_risk.get("unsupported_high_risk_count", 0)
            ),
            "low_info_source_claims_count": int(
                final_claim_risk.get("low_info_source_claims_count", 0)
            ),
            "low_info_source_claim_indices": list(
                final_claim_risk.get("low_info_source_claim_indices", [])
            ),
            "unsupported_high_risk_sentences": list(_unsupported_high_risk_sentences),
            "unsupported_high_risk_low_info_only_count": int(
                final_claim_risk.get("unsupported_high_risk_low_info_only_count", 0)
            ),
            "require_non_low_info_for_high_risk": bool(
                getattr(config, "summary_require_non_low_info_for_high_risk", True)
            ),
            "formula_claims_total": int(final_claim_risk.get("formula_claims_total", 0)),
            "formula_claims_supported": int(
                final_claim_risk.get("formula_claims_supported", 0)
            ),
            "formula_claims_downgraded_to_concept": int(
                final_claim_risk.get("formula_claims_downgraded_to_concept", 0)
            ),
            "formula_mode": _formula_mode,
        },
        "micro_backfill": {
            "triggered": bool(backfill_info.get("triggered", False)),
            "accepted": bool(backfill_info.get("accepted", False)),
            "missing_topics_before": list(backfill_info.get("missing_before", [])),
            "missing_topics_after": list(backfill_info.get("missing_after", [])),
            "paragraphs_attempted": int(backfill_info.get("paragraphs_attempted", 0)),
            "paragraphs_accepted": int(backfill_info.get("paragraphs_accepted", 0)),
            "latency_ms": float(backfill_info.get("latency_ms", 0.0)),
            "rollback_reason": backfill_info.get("rollback_reason"),
            "skipped_topics": list(backfill_info.get("skipped_topics", [])),
            "max_topics_limit": int(getattr(config, "summary_micro_backfill_max_topics", 3)),
        },
        "early_micro_backfill": {
            "triggered": bool(early_backfill_info.get("triggered", False)),
            "accepted": bool(early_backfill_info.get("accepted", False)),
            "missing_topics_before": list(early_backfill_info.get("missing_before", [])),
            "missing_topics_after": list(early_backfill_info.get("missing_after", [])),
            "paragraphs_attempted": int(early_backfill_info.get("paragraphs_attempted", 0)),
            "paragraphs_accepted": int(early_backfill_info.get("paragraphs_accepted", 0)),
            "latency_ms": float(early_backfill_info.get("latency_ms", 0.0)),
            "skipped_reason": early_backfill_info.get("skipped_reason"),
            "backfill_before_deoverreach_enabled": _backfill_before_deoverreach,
        },
        "inference_density": {
            "inference_density": final_inference["inference_density"],
            "inference_threshold": final_inference["inference_threshold"],
            "inference_gate_passed": final_inference["inference_gate_passed"],
            "unsupported_claims_count": final_inference["unsupported_claims_count"],
        },
        "deoverreach": deoverreach_info,
        "corrective_scheduler": {
            "reserve_must_cover_pass_enabled": bool(_reserve_must_cover_pass_enabled),
            "reserve_last_pass_for_must_cover": bool(_reserve_last_pass_for_must_cover),
            "must_cover_missing_at_scheduler": list(_current_outline_missing),
            "backfill_before_deoverreach": _backfill_before_deoverreach,
        },
        "corrective_timeline": list(_corrective_timeline),
        "final": {
            "absolute_weak_ratio_ceiling": round(max_accepted_weak_ratio, 4),
            "absolute_weak_ratio_passed": final_absolute_weak_ratio_passed,
            "final_weak_ratio": round(final_weak_ratio, 4),
            "inference_density": final_inference["inference_density"],
            "missing_topics": list(final_outline_coverage.get("missing_topics", [])),
            # Populated below after evaluating all blocking conditions.
            "accepted": True,
            "blocking_reasons": [],
        },
        # ── Execution metadata ──────────────────────────────────────────────
        "profile_used": _active_profile,
        "corrective_passes_used": _corrective_passes_used,
        "max_corrective_passes": _max_corrective_passes,
        "style_polish_enabled": _style_polish_enabled,
    }
    final_gate_enabled = bool(getattr(config, "summary_final_gate_enabled", False))
    final_gate_reasons: list[str] = []

    # ── Unconditional blocking-reason collection ──────────────────────────────
    # These conditions are always evaluated regardless of final_gate_enabled.
    # They populate diagnostics["final"]["blocking_reasons"] so that callers can
    # detect non-conformance even when the strict gate is disabled.
    _final_blocking_reasons: list[str] = []

    # 1. Absolute weak-ratio ceiling — already evaluated above.
    if not bool(final_structure_info.get("valid", False)):
        _structure_reason = (
            "structure_invalid: "
            f"{str(final_structure_info.get('structure_failure_reason', '')).strip() or 'unknown'}"
        )
        _final_blocking_reasons.append(_structure_reason)
        if final_gate_enabled:
            final_gate_reasons.append("structure_invalid")
        else:
            logger.warning(
                "Deep summary quality warning: %s (final gate disabled, output delivered).",
                _structure_reason,
            )

    if not final_absolute_weak_ratio_passed:
        ceiling_reason = (
            f"final_weak_ratio_exceeded_absolute_ceiling="
            f"{final_weak_ratio:.2f}>{max_accepted_weak_ratio:.2f}"
        )
        _final_blocking_reasons.append(ceiling_reason)
        if final_gate_enabled:
            final_gate_reasons.append(ceiling_reason)
        else:
            logger.warning(
                "Deep summary quality warning: %s (final gate disabled, output delivered).",
                ceiling_reason,
            )

    # 2. Missing must-cover topics — hard gate unconditional on final_gate_enabled.
    #    outline_coverage.missing_topics is the source of truth; a non-empty list
    #    means the pipeline failed to cover at least one mandatory topic.
    _outline_missing_final = list(final_outline_coverage.get("missing_topics", []))
    _outline_must_cover_final = list(final_outline_coverage.get("must_cover_topics", []))
    if _outline_must_cover_final and _outline_missing_final:
        _missing_reason = (
            f"outline_missing_topics_not_allowed: missing={_outline_missing_final}"
        )
        _final_blocking_reasons.append(_missing_reason)
        if final_gate_enabled:
            final_gate_reasons.append(_missing_reason)
        else:
            logger.warning(
                "Deep summary quality warning: %s (final gate disabled, output delivered).",
                _missing_reason,
            )

    # 3. Inference-density gate — high-risk claims without solid source support.
    if not final_inference["inference_gate_passed"]:
        _inference_reason = (
            f"inference_density_exceeded: "
            f"{final_inference['inference_density']:.4f}"
            f" > {final_inference['inference_threshold']:.4f}"
        )
        _final_blocking_reasons.append(_inference_reason)
        if final_gate_enabled:
            final_gate_reasons.append(_inference_reason)
        else:
            logger.warning(
                "Deep summary quality warning: %s (final gate disabled, output delivered).",
                _inference_reason,
            )

    # 4. Unsupported high-risk claims (quantitative/comparative/formula with only
    #    low-info sources or no citation at all).
    _unsupported_hr = int(final_claim_risk.get("unsupported_high_risk_count", 0))
    if _unsupported_hr > 0:
        _hr_reason = (
            f"unsupported_high_risk_claims: count={_unsupported_hr}"
        )
        _final_blocking_reasons.append(_hr_reason)
        if final_gate_enabled:
            final_gate_reasons.append(_hr_reason)
        else:
            logger.warning(
                "Deep summary quality warning: %s (final gate disabled, output delivered).",
                _hr_reason,
            )

    # 4b. High-risk claims supported exclusively by low-info sources.
    #     Reported as a separate blocking reason for auditability. Only fires when
    #     summary_require_non_low_info_for_high_risk=True (already reflected in
    #     unsupported_high_risk_count, but we emit the explicit reason here).
    _unsupported_li_only = int(
        final_claim_risk.get("unsupported_high_risk_low_info_only_count", 0)
    )
    _require_non_low = bool(getattr(config, "summary_require_non_low_info_for_high_risk", True))
    if _require_non_low and _unsupported_li_only > 0:
        _li_reason = (
            f"unsupported_high_risk_low_info_only: count={_unsupported_li_only}"
        )
        # Only add if not already covered by reason 4 (avoids duplicate).
        if _li_reason not in _final_blocking_reasons:
            _final_blocking_reasons.append(_li_reason)
        logger.warning(
            "Deep summary: %d high-risk claim(s) backed only by low-info sources.",
            _unsupported_li_only,
        )

    # Update diagnostics["final"] with conformance result.
    diagnostics["final"]["accepted"] = len(_final_blocking_reasons) == 0
    diagnostics["final"]["blocking_reasons"] = list(_final_blocking_reasons)

    if final_gate_enabled:
        if not bool(final_structure_info.get("valid", False)):
            final_gate_reasons.append("structure_invalid")
        if (
            int(final_grounding_info.get("blocks_with_citations", 0)) > 0
            and final_weak_ratio >= weak_ratio_threshold
        ):
            final_gate_reasons.append(
                f"weak_grounding_ratio={final_weak_ratio:.2f}>={weak_ratio_threshold:.2f}"
            )
        if min_unique_sources > 0 and len(used_source_indices) < min_unique_sources:
            final_gate_reasons.append(
                f"citation_diversity={len(used_source_indices)}<{min_unique_sources}"
            )
        if coverage_gate_enabled and float(final_coverage.get("overall_coverage_score", 1.0)) < coverage_min_score:
            final_gate_reasons.append(
                f"coverage={float(final_coverage.get('overall_coverage_score', 1.0)):.2f}<{coverage_min_score:.2f}"
            )
        if (
            topic_gate_enabled
            and bool(final_topic_coverage.get("required_facets"))
            and float(final_topic_coverage.get("overall_score", 1.0)) < topic_min_score
        ):
            final_gate_reasons.append(
                f"facet_coverage={float(final_topic_coverage.get('overall_score', 1.0)):.2f}<{topic_min_score:.2f}"
            )
        if (
            coverage_gate_enabled
            and bool(final_outline_coverage.get("must_cover_topics"))
            and float(final_outline_coverage.get("overall_score", 1.0)) < outline_min_score
        ):
            final_gate_reasons.append(
                f"outline_coverage={float(final_outline_coverage.get('overall_score', 1.0)):.2f}<{outline_min_score:.2f}"
                f" missing={final_outline_coverage.get('missing_topics', [])}"
            )
        if (
            notation_gate_enabled
            and bool(final_notation.get("active"))
            and float(final_notation.get("score", 1.0)) < notation_min_score
        ):
            final_gate_reasons.append(
                f"notation_fidelity={float(final_notation.get('score', 1.0)):.2f}<{notation_min_score:.2f}"
            )
        if (
            claims_gate_enabled
            and bool(final_critical_claims.get("required_facets"))
            and float(final_critical_claims.get("score", 1.0)) < claims_min_score
        ):
            final_gate_reasons.append(
                f"critical_claims={float(final_critical_claims.get('score', 1.0)):.2f}<{claims_min_score:.2f}"
            )
        if rubric_gate_enabled and float(final_rubric.get("overall_score", 1.0)) < rubric_min_score:
            final_gate_reasons.append(
                f"rubric={float(final_rubric.get('overall_score', 1.0)):.2f}<{rubric_min_score:.2f}"
            )
    diagnostics["final_gate"] = {
        "enabled": final_gate_enabled,
        "passed": len(final_gate_reasons) == 0 if final_gate_enabled else True,
        "reasons": final_gate_reasons,
    }
    if final_gate_enabled and final_gate_reasons:
        logger.warning(
            "Deep summary strict final gate blocked output: %s.",
            "; ".join(final_gate_reasons),
        )
        reason_lines = "\n".join(f"- {reason}" for reason in final_gate_reasons)
        final_text = (
            "# Resumo Aprofundado — bloqueado por qualidade\n\n"
            "O resumo foi bloqueado pelo gate final estrito porque nao atingiu os minimos configurados.\n"
            "Motivos:\n"
            f"{reason_lines}\n\n"
            "Revise os limiares/configuracao ou execute novamente com `debug_summary=true`."
        )
        sources_section = ""
    logger.info(
        "Deep summary diagnostics: profile=%s coverage=%.2f facet=%.2f outline=%.2f "
        "claims=%.2f notation=%.2f rubric=%.2f structure=%s weak_ratio=%.2f "
        "sources=%d/%d resynthesis=%s missing_topics=%s "
        "inference_density=%.4f unsupported_hr=%d deoverreach=%s "
        "final_accepted=%s blocking=%s.",
        diagnostics["coverage_profile"]["name"],
        diagnostics["coverage"]["overall_coverage_score"],
        diagnostics["topic_coverage"]["score"],
        diagnostics["outline_coverage"]["score"],
        diagnostics["critical_claims"]["score"],
        diagnostics["notation_fidelity"]["score"],
        diagnostics["rubric"]["overall_score"],
        diagnostics["structure"]["valid"],
        diagnostics["grounding"]["weak_ratio"],
        diagnostics["citations"]["unique_sources_used"],
        diagnostics["citations"]["anchors_total"],
        "accepted" if diagnostics["resynthesis"]["accepted"] else "not_accepted",
        diagnostics["outline_coverage"]["missing_topics"] or "none",
        diagnostics["inference_density"]["inference_density"],
        diagnostics["claim_risk"]["unsupported_high_risk_count"],
        "accepted" if diagnostics["deoverreach"]["accepted"] else "not_triggered"
        if not diagnostics["deoverreach"]["triggered"] else "rejected",
        diagnostics["final"]["accepted"],
        diagnostics["final"]["blocking_reasons"] or "none",
    )

    # ── Latency / timing ─────────────────────────────────────────────────────
    _total_ms = round((time.monotonic() - _start_ts) * 1000, 1)
    diagnostics["latency"] = {
        "total_ms": _total_ms,
        "stage_timings_ms": dict(_stage_timings),
    }

    logger.info(
        "Deep summary pipeline completed for doc='%s' in %.1fs "
        "(profile=%s, corrective_passes=%d/%d).",
        doc_name,
        _total_ms / 1000,
        _active_profile,
        _corrective_passes_used,
        _max_corrective_passes,
    )
    result = {
        "answer": final_text,
        "sources_section": sources_section,
    }
    # Always attach diagnostics in strict profile so the route/caller can
    # evaluate the fail-closed gate even when include_diagnostics=False.
    if include_diagnostics or _active_profile == "strict":
        result["diagnostics"] = diagnostics
    return result
