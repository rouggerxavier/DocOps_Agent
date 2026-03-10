"""Reranker: rescores retrieved chunks for improved precision.

Two modes:
  - ``local``: Bag-of-words overlap + existing retrieval_score (no API call).
  - ``llm``: Asks the LLM to score each chunk's relevance (slower but better).
"""

import re
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from docops.llm.content import response_text
from docops.logging import get_logger

logger = get_logger("docops.rag.reranker")


# ── Local reranker ─────────────────────────────────────────────────────────

def _bow_score(query: str, text: str) -> float:
    """Bag-of-words overlap: fraction of query tokens found in text."""
    q_tokens = set(re.findall(r"\w+", query.lower()))
    t_tokens = set(re.findall(r"\w+", text.lower()))
    if not q_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / len(q_tokens)


def rerank_local(query: str, docs: List[Document], top_n: int | None = None) -> List[Document]:
    """Rerank documents using a fast local heuristic (no API calls).

    Score = 0.4 * bow_overlap + 0.6 * retrieval_score (if available).
    """
    scored: list[tuple[float, Document]] = []
    for doc in docs:
        bow = _bow_score(query, doc.page_content)
        ret_score = doc.metadata.get("retrieval_score", 0.5)
        combined = 0.4 * bow + 0.6 * ret_score
        doc.metadata["rerank_score"] = round(combined, 4)
        scored.append((combined, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [doc for _, doc in scored]

    if top_n and top_n < len(results):
        results = results[:top_n]

    logger.debug(f"Local rerank: {len(docs)} → {len(results)} docs.")
    return results


# ── LLM reranker ───────────────────────────────────────────────────────────

_RERANK_PROMPT = """\
Avalie a relevância do trecho abaixo para a consulta. \
Responda APENAS com um número de 0.0 a 1.0.

Consulta: {query}

Trecho:
{text}

Relevância (0.0 a 1.0):"""


def _parse_score(raw: str) -> float:
    """Extract a float score from LLM response."""
    match = re.search(r"([01](?:\.\d+)?)", raw.strip())
    if match:
        return float(match.group(1))
    return 0.5  # fallback


def rerank_llm(query: str, docs: List[Document], llm, top_n: int | None = None) -> List[Document]:
    """Rerank documents by asking the LLM to score each chunk's relevance.

    More accurate but costs one LLM call per chunk.
    """
    scored: list[tuple[float, Document]] = []

    for doc in docs:
        text_preview = doc.page_content[:800]
        prompt = _RERANK_PROMPT.format(query=query, text=text_preview)
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            score = _parse_score(response_text(response))
        except Exception as exc:
            logger.warning(f"LLM rerank failed for chunk: {exc}")
            score = 0.5

        doc.metadata["rerank_score"] = round(score, 4)
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [doc for _, doc in scored]

    if top_n and top_n < len(results):
        results = results[:top_n]

    logger.debug(f"LLM rerank: {len(docs)} → {len(results)} docs.")
    return results
