"""Hybrid search: BM25 lexical + vector semantic retrieval with RRF fusion.

During ingestion, a BM25 index is built from chunk texts and persisted to disk.
At query time, both BM25 and vector results are merged using Reciprocal Rank
Fusion (RRF) for balanced lexical+semantic retrieval.
"""

import json
import pickle
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from docops.config import config
from docops.logging import get_logger

logger = get_logger("docops.rag.hybrid")


# ── BM25 index persistence ─────────────────────────────────────────────────

def _bm25_path() -> Path:
    """Return the path to the persisted BM25 index file."""
    bm25_dir = config.bm25_dir
    bm25_dir.mkdir(parents=True, exist_ok=True)
    return bm25_dir / "bm25_index.pkl"


def _corpus_path() -> Path:
    """Return the path to the persisted BM25 corpus metadata."""
    return _bm25_path().with_suffix(".json")


def build_bm25_index(chunks: List[Document]) -> None:
    """Build and persist a BM25 index from document chunks.

    Called during ingestion. Stores both the BM25 model and the
    corpus mapping (chunk_id → text + metadata) for retrieval.
    """
    from rank_bm25 import BM25Okapi

    tokenized = [doc.page_content.lower().split() for doc in chunks]
    bm25 = BM25Okapi(tokenized)

    # Save BM25 model
    with open(_bm25_path(), "wb") as f:
        pickle.dump(bm25, f)

    # Save corpus metadata for reconstruction
    corpus = []
    for doc in chunks:
        corpus.append({
            "chunk_id": doc.metadata.get("chunk_id", ""),
            "text": doc.page_content,
            "metadata": {k: str(v) for k, v in doc.metadata.items()},
        })
    with open(_corpus_path(), "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False)

    logger.info(f"BM25 index built: {len(chunks)} chunks → {_bm25_path()}")


def _load_bm25():
    """Load the persisted BM25 index and corpus."""
    from rank_bm25 import BM25Okapi  # noqa: F811

    idx_path = _bm25_path()
    corp_path = _corpus_path()

    if not idx_path.exists() or not corp_path.exists():
        logger.warning("BM25 index not found. Run ingestion first.")
        return None, []

    with open(idx_path, "rb") as f:
        bm25 = pickle.load(f)  # noqa: S301

    with open(corp_path, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    return bm25, corpus


def bm25_search(query: str, k: int = 6) -> List[Document]:
    """Search the BM25 index and return the top-k results as Documents."""
    bm25, corpus = _load_bm25()
    if bm25 is None:
        return []

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    # Get top-k indices
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

    results: list[Document] = []
    for idx in ranked:
        if idx < len(corpus):
            entry = corpus[idx]
            meta = entry.get("metadata", {})
            meta["bm25_score"] = round(float(scores[idx]), 4)
            meta["retrieval_mode"] = "bm25"
            results.append(Document(page_content=entry["text"], metadata=meta))

    logger.debug(f"BM25 search: {len(results)} results for '{query[:50]}'.")
    return results


# ── Reciprocal Rank Fusion ─────────────────────────────────────────────────

def reciprocal_rank_fusion(
    result_lists: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    """Merge multiple ranked result lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum(1 / (k + rank)) across all lists where the doc appears.
    Documents are identified by chunk_id; those without chunk_id are kept
    but not deduplicated.
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}
    no_id_docs: list[tuple[float, Document]] = []

    for result_list in result_lists:
        for rank, doc in enumerate(result_list):
            cid = doc.metadata.get("chunk_id")
            rrf = 1.0 / (k + rank + 1)

            if cid:
                scores[cid] = scores.get(cid, 0.0) + rrf
                if cid not in doc_map:
                    doc_map[cid] = doc
            else:
                no_id_docs.append((rrf, doc))

    # Sort by RRF score descending
    sorted_ids = sorted(scores, key=scores.get, reverse=True)
    results: list[Document] = []
    for cid in sorted_ids:
        doc = doc_map[cid]
        doc.metadata["rrf_score"] = round(scores[cid], 6)
        results.append(doc)

    # Append docs without chunk_id at the end
    for rrf_score, doc in no_id_docs:
        doc.metadata["rrf_score"] = round(rrf_score, 6)
        results.append(doc)

    return results


def hybrid_retrieve(
    query: str,
    vector_fn,
    k_vec: int | None = None,
    k_lex: int | None = None,
    alpha: float | None = None,
) -> list[Document]:
    """Retrieve using both vector and BM25, fusing with RRF.

    Args:
        query: User query.
        vector_fn: Callable(query, top_k) -> List[Document] for vector search.
        k_vec: Number of vector results. Defaults to config.top_k.
        k_lex: Number of BM25 results. Defaults to config.hybrid_k_lex.
        alpha: Not used directly (RRF handles fusion), reserved for future weighting.

    Returns:
        Fused list of Documents, sorted by RRF score.
    """
    k_v = k_vec or config.top_k
    k_l = k_lex or config.hybrid_k_lex

    vec_results = vector_fn(query, k_v)
    lex_results = bm25_search(query, k=k_l)

    fused = reciprocal_rank_fusion([vec_results, lex_results])

    logger.debug(
        f"Hybrid retrieve: {len(vec_results)} vector + {len(lex_results)} BM25 "
        f"→ {len(fused)} fused results."
    )
    return fused
