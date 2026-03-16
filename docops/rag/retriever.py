"""Retrieval logic for similarity, MMR, and hybrid search.

Primary flow is user-scoped retrieval. Legacy global compatibility remains for
calls that omit user_id (treated as user_id=0).
"""

from __future__ import annotations

from typing import List

from langchain_core.documents import Document

from docops.config import config
from docops.ingestion.indexer import get_vectorstore, get_vectorstore_for_user
from docops.llm.router import build_chat_model
from docops.logging import get_logger

logger = get_logger("docops.rag.retriever")


def _get_vs_for_user(user_id: int):
    """Return user-scoped vectorstore."""
    return get_vectorstore_for_user(user_id)


def _get_vs():
    """Legacy/global vectorstore accessor (user_id=0)."""
    return get_vectorstore()


def _resolve_vs(user_id: int):
    if user_id <= 0:
        return _get_vs()
    return _get_vs_for_user(user_id)


def _passes_score_gate(vectorstore, query: str, threshold: float) -> bool:
    """Check whether best similarity score meets threshold."""
    try:
        results = vectorstore.similarity_search_with_relevance_scores(query, k=1)
    except NotImplementedError:
        logger.debug("Score gate unavailable, skipping.")
        return True
    except Exception as exc:
        logger.warning("Score gate failed: %s", exc)
        return True

    if not results:
        return False

    _, best_score = results[0]
    return best_score >= threshold


def _similarity_search_with_scores(vectorstore, query: str, k: int, threshold: float) -> List[Document]:
    """Run similarity search and apply score filtering."""
    try:
        results = vectorstore.similarity_search_with_relevance_scores(query, k=k)
    except NotImplementedError:
        return vectorstore.similarity_search(query, k=k)
    except Exception as exc:
        logger.error("Similarity search failed: %s", exc)
        return []

    docs: list[Document] = []
    for doc, score in results:
        if score >= threshold:
            doc.metadata["retrieval_score"] = round(score, 4)
            docs.append(doc)

    return docs


def _mmr_search(vectorstore, query: str, k: int, threshold: float) -> List[Document]:
    """Run MMR retrieval with score gate and fallback."""
    if not _passes_score_gate(vectorstore, query, threshold):
        return []

    fetch_k = max(config.mmr_fetch_k, k * 2)
    lambda_mult = config.mmr_lambda

    try:
        docs = vectorstore.max_marginal_relevance_search(
            query,
            k=k,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
        )
    except (NotImplementedError, AttributeError):
        logger.warning("MMR unavailable, falling back to similarity search.")
        return _similarity_search_with_scores(vectorstore, query, k, threshold)
    except Exception as exc:
        logger.error("MMR search failed: %s", exc)
        return []

    for doc in docs:
        doc.metadata["retrieval_mode"] = "mmr"

    return docs


def _base_retrieve(query: str, user_id: int = 0, top_k: int | None = None) -> List[Document]:
    """Core retriever without query rewriting or reranking."""
    k = top_k if top_k is not None else config.top_k
    threshold = config.min_relevance_score
    mode = config.retrieval_mode

    vectorstore = _resolve_vs(user_id)

    if mode == "hybrid":
        from docops.rag.hybrid import hybrid_retrieve_for_user

        docs = hybrid_retrieve_for_user(
            user_id=user_id,
            query=query,
            vector_fn=lambda q, kk: _similarity_search_with_scores(
                vectorstore,
                q,
                kk or k,
                threshold,
            ),
            k_vec=k,
        )
    elif mode == "mmr":
        docs = _mmr_search(vectorstore, query, k, threshold)
    else:
        docs = _similarity_search_with_scores(vectorstore, query, k, threshold)

    return docs


def retrieve(query: str, user_id: int = 0, top_k: int | None = None) -> List[Document]:
    """Retrieve chunks for a query, scoped to a user."""
    if config.multi_query:
        from docops.rag.query_rewrite import multi_query_retrieve

        llm = build_chat_model(route="cheap", temperature=0.3)
        docs = multi_query_retrieve(
            query=query,
            retriever_fn=lambda q, k=None: _base_retrieve(q, user_id=user_id, top_k=k),
            llm=llm,
            n_variations=config.multi_query_n,
            per_query_k=config.multi_query_per_query_k,
        )
    else:
        docs = _base_retrieve(query, user_id=user_id, top_k=top_k)

    if config.reranker != "none" and docs:
        from docops.rag.reranker import rerank_local, rerank_llm

        top_n = config.rerank_top_n
        if config.reranker == "llm":
            llm = build_chat_model(route="cheap", temperature=0.0)
            docs = rerank_llm(query, docs, llm, top_n=top_n)
        else:
            docs = rerank_local(query, docs, top_n=top_n)

    return docs


def retrieve_for_doc(
    doc_name_or_id: str,
    query: str,
    top_k: int | None = None,
    user_id: int = 0,
    doc_id: str | None = None,
) -> List[Document]:
    """Retrieve chunks restricted to one document in one tenant."""
    k = top_k if top_k is not None else config.top_k
    vectorstore = _resolve_vs(user_id)

    try:
        if doc_id:
            return vectorstore.similarity_search(query, k=k, filter={"doc_id": doc_id})

        docs = vectorstore.similarity_search(query, k=k, filter={"file_name": doc_name_or_id})
        if docs:
            return docs

        # Fallback when caller passed doc_id in the first argument.
        return vectorstore.similarity_search(query, k=k, filter={"doc_id": doc_name_or_id})
    except Exception as exc:
        logger.error("Filtered retrieval failed: %s", exc)
        return []


def retrieve_for_docs(
    doc_names_or_ids: list[str],
    query: str,
    top_k: int | None = None,
    user_id: int = 0,
    doc_ids: list[str] | None = None,
    per_doc_k: int | None = None,
) -> List[Document]:
    """Retrieve chunks restricted to a list of documents in one tenant.

    If ``per_doc_k`` is provided, each selected document retrieves up to that
    amount and the merged list is returned (deduplicated). Otherwise, ``top_k``
    is treated as a global cap across selected documents.
    """
    names = [str(name).strip() for name in (doc_names_or_ids or []) if str(name).strip()]
    ids = [str(doc_id).strip() for doc_id in (doc_ids or []) if str(doc_id).strip()]
    if not names and not ids:
        return []

    targets: list[tuple[str, str | None]] = []
    if ids:
        for idx, doc_id in enumerate(ids):
            name = names[idx] if idx < len(names) else doc_id
            targets.append((name, doc_id))
    else:
        for name in names:
            targets.append((name, None))

    if not targets:
        return []

    total_k = top_k if top_k is not None else config.top_k
    each_k = per_doc_k if per_doc_k is not None else max(1, total_k)

    merged: list[Document] = []
    for name, doc_id in targets:
        docs = retrieve_for_doc(
            name,
            query=query,
            top_k=each_k,
            user_id=user_id,
            doc_id=doc_id,
        )
        for doc in docs:
            doc.metadata["retrieval_mode"] = "filtered_multi_doc"
        merged.extend(docs)

    seen: set[str] = set()
    unique_docs: list[Document] = []
    for doc in merged:
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        identity = str(
            meta.get("chunk_id")
            or f"{meta.get('doc_id','')}|{meta.get('page_start','')}|{meta.get('chunk_index','')}|{hash(doc.page_content)}"
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique_docs.append(doc)

    if per_doc_k is None:
        return unique_docs[:total_k]
    return unique_docs
