"""Query rewriting and multi-query retrieval for improved recall.

Generates N query variations using the LLM, retrieves for each, and
deduplicates the results by chunk_id so broader evidence is collected.
"""

from typing import Callable, List

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from docops.llm.content import response_text
from docops.logging import get_logger

logger = get_logger("docops.rag.query_rewrite")

_REWRITE_PROMPT = """\
Você é um assistente de busca. Dada a consulta abaixo, gere {n} variações \
reformuladas que preservem o significado original mas usem sinônimos, \
reestruturações ou perspectivas diferentes. Retorne APENAS as variações, \
uma por linha, sem numeração nem explicação.

Consulta: {query}"""


def rewrite_queries(query: str, llm, n: int = 3) -> list[str]:
    """Generate *n* reformulated variations of *query* using the LLM.

    Returns a list of variation strings (may be fewer than *n* if parsing
    fails). The original query is **not** included in the output.
    """
    prompt = _REWRITE_PROMPT.format(query=query, n=n)
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response_text(response)
    except Exception as exc:
        logger.warning(f"Query rewrite failed ({exc}); returning empty list.")
        return []

    variations: list[str] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("0123456789.-) ")
        if line and line.lower() != query.lower():
            variations.append(line)

    logger.debug(f"Rewrote '{query[:50]}' into {len(variations)} variations.")
    return variations[:n]


def multi_query_retrieve(
    query: str,
    retriever_fn: Callable[[str, int | None], List[Document]],
    llm,
    n_variations: int = 3,
    per_query_k: int | None = None,
) -> List[Document]:
    """Retrieve using the original query plus *n_variations* rewrites.

    Deduplicates results by ``chunk_id`` metadata. Documents without a
    chunk_id are kept but not deduplicated.

    Args:
        query: Original user query.
        retriever_fn: Callable(query, top_k) -> List[Document].
        llm: LLM instance for rewriting.
        n_variations: Number of query rewrites.
        per_query_k: top_k per individual retrieval call.

    Returns:
        Deduplicated list of Documents.
    """
    all_queries = [query] + rewrite_queries(query, llm, n=n_variations)
    logger.debug(f"Multi-query: {len(all_queries)} total queries.")

    seen_ids: set[str] = set()
    results: list[Document] = []

    for q in all_queries:
        docs = retriever_fn(q, per_query_k)
        for doc in docs:
            cid = doc.metadata.get("chunk_id")
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            results.append(doc)

    logger.debug(f"Multi-query retrieval: {len(results)} unique docs from {len(all_queries)} queries.")
    return results
