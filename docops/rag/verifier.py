"""Grounding verifier: checks that answers are properly cited and evidence-backed."""

import re
from typing import TYPE_CHECKING

from docops.config import config
from docops.logging import get_logger
from docops.rag.citations import count_citations_in_answer, max_citation_index

if TYPE_CHECKING:
    from docops.graph.state import AgentState

logger = get_logger("docops.rag.verifier")

# Patterns that suggest a "factual" answer requiring citations
_FACTUAL_PATTERNS = [
    r"\b\d{4}\b",           # years (e.g., 2023)
    r"\b\d+[\.,]\d+\b",     # decimal numbers
    r"\b\d+%",              # percentages
    r"\bsegundo\b",         # "according to"
    r"\bconforme\b",        # "according to"
    r"\bde acordo com\b",   # "according to"
    r"\bporque\b",          # "because" — causal claims
    r"\bportanto\b",        # "therefore"
    r"\bconcluí\b",         # "I concluded"
    r"\bdefine(-se)?\b",    # definitions
    r"\bé composto\b",      # compositional claims
    r"\bresultou\b",        # results/findings
]

_FACTUAL_RE = re.compile("|".join(_FACTUAL_PATTERNS), re.IGNORECASE)


def is_factual_answer(answer: str) -> bool:
    """Heuristic: does the answer contain factual claims that require citations?"""
    return bool(_FACTUAL_RE.search(answer))


def has_min_citations(answer: str, min_cites: int | None = None) -> bool:
    """Check whether the answer has at least min_cites [Fonte N] references."""
    required = min_cites if min_cites is not None else config.min_citations
    found = count_citations_in_answer(answer)
    return found >= required


def verify_grounding(state: "AgentState") -> dict:
    """Verify that the synthesized answer is properly grounded.

    Returns a dict with:
    - ``grounding_ok``: bool — True if verification passed
    - ``retry``: bool — True if we should retry with higher top_k
    - ``disclaimer``: str — message to append if evidence is weak
    """
    answer = state.get("answer", "")
    retry_count = state.get("retry_count", 0)

    # Short circuit: if there are no retrieved docs, it can't be grounded
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        logger.warning("No retrieved chunks — grounding check fails.")
        return {
            "grounding_ok": False,
            "retry": retry_count < config.max_retries,
            "disclaimer": (
                "\n\n> ⚠️ **Aviso:** Não foram encontrados trechos relevantes nos documentos "
                "indexados. Verifique se os documentos corretos foram ingeridos e tente "
                "reformular sua pergunta."
            ),
        }

    # Check if answer is factual and needs citations
    factual = is_factual_answer(answer)
    cites_ok = has_min_citations(answer)

    if not factual:
        # Non-factual answer (e.g., "I don't know") — no citation required
        logger.debug("Answer is non-factual; grounding check passes.")
        return {"grounding_ok": True, "retry": False, "disclaimer": ""}

    # Check for phantom citations: [Fonte N] where N > number of chunks
    max_idx = max_citation_index(answer)
    if max_idx > len(chunks):
        logger.warning(
            f"Phantom citation detected: [Fonte {max_idx}] but only {len(chunks)} chunks."
        )
        if retry_count < config.max_retries:
            return {"grounding_ok": False, "retry": True, "disclaimer": ""}
        return {
            "grounding_ok": False,
            "retry": False,
            "disclaimer": (
                "\n\n> ⚠️ **Aviso:** A resposta referencia fontes inexistentes. "
                "Os resultados podem não ser confiáveis."
            ),
        }

    if cites_ok:
        logger.debug("Answer has sufficient citations; grounding check passes.")
        return {"grounding_ok": True, "retry": False, "disclaimer": ""}

    # Factual answer but missing citations
    found_cites = count_citations_in_answer(answer)
    logger.warning(
        f"Grounding check failed: found {found_cites} citation(s), "
        f"need {config.min_citations}. retry_count={retry_count}"
    )

    if retry_count < config.max_retries:
        return {
            "grounding_ok": False,
            "retry": True,
            "disclaimer": "",
        }

    # Max retries exhausted
    return {
        "grounding_ok": False,
        "retry": False,
        "disclaimer": (
            "\n\n> ⚠️ **Aviso de baixa evidência:** Esta resposta pode não estar "
            "completamente suportada pelos documentos disponíveis. "
            "Considere adicionar mais documentos relevantes ou reformular a consulta."
        ),
    }
