"""Retrieval logic: similarity/MMR/hybrid search against the Chroma vector store.

Supports three modes (set via RETRIEVAL_MODE env var):
  - ``mmr`` (default): Max Marginal Relevance — diverse retrieval
  - ``similarity``: Standard cosine similarity search
  - ``hybrid``: BM25 lexical + vector semantic with RRF fusion

All modes apply a minimum relevance score threshold (MIN_RELEVANCE_SCORE)
to avoid injecting weak/irrelevant evidence into the LLM context.

Optional features (via env vars):
  - Multi-query retrieval (MULTI_QUERY=true): rewrites the query into N
    variations for broader recall, then deduplicates results.
  - Reranking (RERANKER=local|llm): rescores retrieved chunks for precision.
"""

from typing import List

from langchain_core.documents import Document

from docops.config import config
from docops.ingestion.indexer import get_vectorstore
from docops.logging import get_logger

logger = get_logger("docops.rag.retriever")


def _get_vs():
    """Return the Chroma vector store."""
    return get_vectorstore()


def _passes_score_gate(vectorstore, query: str, threshold: float) -> bool:
    """Quick relevance gate: check if the best result meets the minimum score.

    Used before MMR (which doesn't return scores) to ensure we have at least
    some relevant content in the index.
    """
    try:
        results = vectorstore.similarity_search_with_relevance_scores(query, k=1)
    except NotImplementedError:
        # Fallback: if the vectorstore doesn't support scores, allow through
        logger.debug("Score gate: similarity_search_with_relevance_scores not available, skipping.")
        return True
    except Exception as exc:
        logger.warning(f"Score gate check failed: {exc}")
        return True  # fail-open: don't block retrieval on gate errors

    if not results:
        logger.debug("Score gate: no results returned.")
        return False

    _doc, best_score = results[0]
    logger.debug(f"Score gate: best_score={best_score:.4f}, threshold={threshold}")
    return best_score >= threshold


def _similarity_search_with_scores(
    vectorstore, query: str, k: int, threshold: float
) -> List[Document]:
    """Similarity search with score filtering."""
    try:
        results = vectorstore.similarity_search_with_relevance_scores(query, k=k)
    except NotImplementedError:
        # Fallback to plain similarity_search if scores not available
        logger.debug("Falling back to plain similarity_search (no scores).")
        return vectorstore.similarity_search(query, k=k)
    except Exception as exc:
        logger.error(f"Similarity search failed: {exc}")
        return []

    docs = []
    for doc, score in results:
        if score >= threshold:
            doc.metadata["retrieval_score"] = round(score, 4)
            docs.append(doc)
        else:
            logger.debug(
                f"Filtered out chunk (score={score:.4f} < {threshold}): "
                f"'{doc.page_content[:50]}'"
            )

    return docs


def _mmr_search(vectorstore, query: str, k: int, threshold: float) -> List[Document]:
    """MMR search with score-based gating.

    MMR itself doesn't return scores, so we first check the score gate
    to ensure there's relevant content, then run MMR for diversity.
    """
    # Gate check: reject if best result is below threshold
    if not _passes_score_gate(vectorstore, query, threshold):
        logger.info("MMR gated: best score below threshold, returning [].")
        return []

    fetch_k = max(config.mmr_fetch_k, k * 2)
    lambda_mult = config.mmr_lambda

    try:
        docs = vectorstore.max_marginal_relevance_search(
            query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult
        )
    except (NotImplementedError, AttributeError):
        logger.warning("MMR not available, falling back to similarity search.")
        return _similarity_search_with_scores(vectorstore, query, k, threshold)
    except Exception as exc:
        logger.error(f"MMR search failed: {exc}")
        return []

    # Annotate docs with mode info for debugging
    for doc in docs:
        doc.metadata["retrieval_mode"] = "mmr"

    return docs


def _base_retrieve(query: str, top_k: int | None = None) -> List[Document]:
    """Core retrieval dispatcher (single query, no rewriting/reranking)."""
    k = top_k if top_k is not None else config.top_k
    mode = config.retrieval_mode
    threshold = config.min_relevance_score
    vectorstore = _get_vs()

    logger.debug(f"Retrieval: mode={mode}, top_k={k}, threshold={threshold}")

    if mode == "hybrid":
        from docops.rag.hybrid import hybrid_retrieve
        docs = hybrid_retrieve(query, vector_fn=lambda q, kk: _similarity_search_with_scores(
            vectorstore, q, kk or k, threshold
        ), k_vec=k)
    elif mode == "mmr":
        docs = _mmr_search(vectorstore, query, k, threshold)
    else:
        docs = _similarity_search_with_scores(vectorstore, query, k, threshold)

    logger.debug(
        f"Retrieved {len(docs)} chunks (mode={mode}, threshold={threshold}) "
        f"for query: '{query[:60]}'"
    )
    return docs


def retrieve(query: str, top_k: int | None = None) -> List[Document]:
    """Retrieve the top-k most relevant chunks for a query.

    Applies the configured retrieval mode, optional multi-query expansion,
    and optional reranking.

    Args:
        query: The user's query string.
        top_k: Number of chunks to retrieve. Defaults to config.top_k.

    Returns:
        List of Document objects with metadata (source, file_name, page, chunk_id).
        Empty list if no results pass the relevance threshold.
    """
    # Multi-query retrieval
    if config.multi_query:
        from docops.rag.query_rewrite import multi_query_retrieve
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=config.gemini_model,
            google_api_key=config.gemini_api_key,
            temperature=0.3,
        )
        docs = multi_query_retrieve(
            query=query,
            retriever_fn=_base_retrieve,
            llm=llm,
            n_variations=config.multi_query_n,
            per_query_k=config.multi_query_per_query_k,
        )
    else:
        docs = _base_retrieve(query, top_k)

    # Reranking
    reranker_mode = config.reranker
    if reranker_mode != "none" and docs:
        from docops.rag.reranker import rerank_local, rerank_llm

        top_n = config.rerank_top_n
        if reranker_mode == "llm":
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=config.gemini_model,
                google_api_key=config.gemini_api_key,
                temperature=0.0,
            )
            docs = rerank_llm(query, docs, llm, top_n=top_n)
        else:
            docs = rerank_local(query, docs, top_n=top_n)

    return docs


def retrieve_for_doc(doc_name: str, query: str, top_k: int | None = None) -> List[Document]:
    """Retrieve chunks filtered to a specific document (by file_name).

    Uses Chroma's server-side metadata filter for efficiency.
    Falls back to plain similarity_search (no MMR/threshold) for simplicity
    since filtered queries are targeted and expected to be relevant.

    Args:
        doc_name: The file_name to filter by (e.g. 'manual.pdf').
        query: Query string.
        top_k: Number of results.

    Returns:
        List of matching Document chunks.
    """
    k = top_k if top_k is not None else config.top_k
    vectorstore = _get_vs()

    try:
        docs = vectorstore.similarity_search(
            query,
            k=k,
            filter={"file_name": doc_name},
        )
        logger.debug(
            f"Retrieved {len(docs)} chunks from '{doc_name}' for query: '{query[:60]}'"
        )
        return docs
    except Exception as exc:
        logger.error(f"Filtered retrieval failed: {exc}")
        return []
