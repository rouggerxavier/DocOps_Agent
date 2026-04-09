"""Hybrid retrieval utilities: per-user BM25 + vector fusion.

Primary path is multi-tenant via user-scoped BM25 directories.
Legacy global helpers remain available for backward compatibility (user_id=0).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from docops.config import config
from docops.logging import get_logger
from docops.storage.paths import get_user_bm25_dir

logger = get_logger("docops.rag.hybrid")


def _bm25_path() -> Path:
    """Legacy/global BM25 index path."""
    config.bm25_dir.mkdir(parents=True, exist_ok=True)
    return config.bm25_dir / "bm25_index.pkl"


def _corpus_path() -> Path:
    """Legacy/global BM25 corpus path."""
    return _bm25_path().with_suffix(".json")


def _bm25_path_for_user(user_id: int) -> Path:
    """Return BM25 index path for a specific user."""
    if user_id <= 0:
        return _bm25_path()
    user_dir = get_user_bm25_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "bm25_index.pkl"


def _corpus_path_for_user(user_id: int) -> Path:
    """Return BM25 corpus path for a specific user."""
    if user_id <= 0:
        return _corpus_path()
    return _bm25_path_for_user(user_id).with_suffix(".json")


def clear_bm25_index_for_user(user_id: int) -> None:
    """Delete BM25 index/corpus files for a user."""
    idx_path = _bm25_path_for_user(user_id)
    corp_path = _corpus_path_for_user(user_id)
    idx_path.unlink(missing_ok=True)
    corp_path.unlink(missing_ok=True)


def build_bm25_index_for_user(user_id: int, chunks: List[Document]) -> None:
    """Build and persist a BM25 index from chunks for one user."""
    if not chunks:
        clear_bm25_index_for_user(user_id)
        logger.info("BM25 index cleared for user %s (empty corpus).", user_id)
        return

    from rank_bm25 import BM25Okapi

    tokenized = [doc.page_content.lower().split() for doc in chunks]
    bm25 = BM25Okapi(tokenized)

    idx_path = _bm25_path_for_user(user_id)
    corp_path = _corpus_path_for_user(user_id)
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    corp_path.parent.mkdir(parents=True, exist_ok=True)

    with open(idx_path, "wb") as handle:
        pickle.dump(bm25, handle)

    corpus = []
    for doc in chunks:
        corpus.append(
            {
                "chunk_id": doc.metadata.get("chunk_id", ""),
                "text": doc.page_content,
                "metadata": dict(doc.metadata),
            }
        )

    with open(corp_path, "w", encoding="utf-8") as handle:
        json.dump(corpus, handle, ensure_ascii=False)

    logger.info(
        "BM25 index built for user %s: %s chunks -> %s",
        user_id,
        len(chunks),
        idx_path,
    )


def build_bm25_index(chunks: List[Document]) -> None:
    """Legacy global BM25 build (user_id=0)."""
    build_bm25_index_for_user(user_id=0, chunks=chunks)


def _load_bm25_for_user(user_id: int):
    """Load BM25 index and corpus for one user."""
    idx_path = _bm25_path_for_user(user_id)
    corp_path = _corpus_path_for_user(user_id)

    if not idx_path.exists() or not corp_path.exists():
        logger.warning("BM25 index not found for user %s. Run ingestion first.", user_id)
        return None, []

    with open(idx_path, "rb") as handle:
        bm25 = pickle.load(handle)  # noqa: S301
    with open(corp_path, "r", encoding="utf-8") as handle:
        corpus = json.load(handle)

    return bm25, corpus


def load_bm25_index_for_user(user_id: int):
    """Public loader helper for tests/services."""
    return _load_bm25_for_user(user_id)


def bm25_search_for_user(user_id: int, query: str, k: int = 6) -> List[Document]:
    """Search user BM25 index and return top-k documents."""
    bm25, corpus = _load_bm25_for_user(user_id)
    if bm25 is None:
        return []

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)
    ranked = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)[:k]

    results: list[Document] = []
    for idx in ranked:
        if idx >= len(corpus):
            continue
        entry = corpus[idx]
        metadata = dict(entry.get("metadata", {}))
        metadata["bm25_score"] = round(float(scores[idx]), 4)
        metadata["retrieval_mode"] = "bm25"
        results.append(Document(page_content=entry.get("text", ""), metadata=metadata))

    return results


def bm25_search(query: str, k: int = 6) -> List[Document]:
    """Legacy global BM25 search (user_id=0)."""
    return bm25_search_for_user(user_id=0, query=query, k=k)


def reciprocal_rank_fusion(result_lists: list[list[Document]], k: int = 60) -> list[Document]:
    """Fuse multiple ranked lists with Reciprocal Rank Fusion (RRF)."""
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}
    no_id_docs: list[tuple[float, Document]] = []

    for result_list in result_lists:
        for rank, doc in enumerate(result_list):
            chunk_id = doc.metadata.get("chunk_id")
            rrf_score = 1.0 / (k + rank + 1)

            if chunk_id:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score
                if chunk_id not in doc_map:
                    doc_map[chunk_id] = doc
            else:
                no_id_docs.append((rrf_score, doc))

    ordered_ids = sorted(scores, key=scores.get, reverse=True)
    fused: list[Document] = []

    for chunk_id in ordered_ids:
        doc = doc_map[chunk_id]
        doc.metadata["rrf_score"] = round(scores[chunk_id], 6)
        fused.append(doc)

    for rrf_score, doc in no_id_docs:
        doc.metadata["rrf_score"] = round(rrf_score, 6)
        fused.append(doc)

    return fused


def hybrid_retrieve_for_user(
    user_id: int,
    query: str,
    vector_fn,
    k_vec: int | None = None,
    k_lex: int | None = None,
    alpha: float | None = None,
) -> list[Document]:
    """Run hybrid retrieval for one user and merge results via RRF."""
    del alpha  # RRF path currently does not use weighted blending.

    k_vector = k_vec or config.top_k
    k_lexical = k_lex or config.hybrid_k_lex

    vector_results = vector_fn(query, k_vector)
    lexical_results = bm25_search_for_user(user_id, query, k=k_lexical)

    fused = reciprocal_rank_fusion([vector_results, lexical_results])
    logger.debug(
        "Hybrid retrieve user=%s: %s vector + %s bm25 -> %s fused",
        user_id,
        len(vector_results),
        len(lexical_results),
        len(fused),
    )
    return fused


def hybrid_retrieve(
    query: str,
    vector_fn,
    k_vec: int | None = None,
    k_lex: int | None = None,
    alpha: float | None = None,
) -> list[Document]:
    """Legacy global hybrid retrieval (user_id=0)."""
    return hybrid_retrieve_for_user(
        user_id=0,
        query=query,
        vector_fn=vector_fn,
        k_vec=k_vec,
        k_lex=k_lex,
        alpha=alpha,
    )
