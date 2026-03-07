"""Indexer: persists document chunks into per-user Chroma vector store collections.

Each user gets their own Chroma collection (docops_user_<id>),
ensuring complete data isolation at the vector store level.

Supports incremental ingestion: when INGEST_INCREMENTAL=true, existing
chunks with the same ID are skipped (upsert semantics via stable IDs).
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from docops.config import config
from docops.ingestion.metadata import build_embedding_text, normalize_chunk_metadata
from docops.logging import get_logger
from docops.storage.paths import get_user_collection_name

logger = get_logger("docops.ingestion.indexer")


# ── Embeddings ────────────────────────────────────────────────────────────────

def _get_embeddings():
    """Return Google Generative AI embeddings."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=config.gemini_api_key,
    )


# ── Chroma vector store ───────────────────────────────────────────────────────

def get_vectorstore_for_user(user_id: int, embeddings=None):
    """Return a Chroma vector store scoped to a specific user.

    Each user has a dedicated collection named ``docops_user_<id>``.
    """
    if user_id <= 0:
        # Legacy/global compatibility path (used by historical tests and CLI).
        return get_vectorstore(embeddings=embeddings)

    from langchain_chroma import Chroma

    chroma_dir = config.chroma_dir
    chroma_dir.mkdir(parents=True, exist_ok=True)

    emb = embeddings or _get_embeddings()
    collection_name = get_user_collection_name(user_id)
    return Chroma(
        collection_name=collection_name,
        embedding_function=emb,
        persist_directory=str(chroma_dir),
    )


def get_vectorstore(embeddings=None):
    """Legacy global vectorstore — kept only for CLI/non-authenticated paths.

    Prefer get_vectorstore_for_user() in all authenticated contexts.
    """
    from langchain_chroma import Chroma

    chroma_dir = config.chroma_dir
    chroma_dir.mkdir(parents=True, exist_ok=True)

    emb = embeddings or _get_embeddings()
    return Chroma(
        collection_name="docops",
        embedding_function=emb,
        persist_directory=str(chroma_dir),
    )


# ── Manifest for incremental ingest ──────────────────────────────────────────

def _manifest_path(user_id: int) -> Path:
    return config.chroma_dir / f"ingest_manifest_user_{user_id}.json"


def _load_manifest(user_id: int) -> dict:
    """Load the per-user ingestion manifest (chunk_id -> file_name mapping)."""
    p = _manifest_path(user_id)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(user_id: int, manifest: dict) -> None:
    """Persist the per-user ingestion manifest."""
    p = _manifest_path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def index_chunks_for_user(
    user_id: int,
    chunks: List[Document],
    embeddings=None,
    incremental: bool | None = None,
) -> int:
    """Add chunks to the user's Chroma collection and return count of indexed chunks."""
    if not chunks:
        logger.warning("No chunks to index.")
        return 0

    use_incremental = incremental if incremental is not None else config.ingest_incremental

    normalized_chunks: list[Document] = []
    for i, chunk in enumerate(chunks):
        cloned = Document(
            page_content=chunk.page_content,
            metadata=deepcopy(chunk.metadata),
        )
        normalize_chunk_metadata(cloned, chunk_index=i, stable_ids=True, user_id=user_id)
        normalized_chunks.append(cloned)
    chunks = normalized_chunks

    if use_incremental:
        manifest = _load_manifest(user_id)
        new_chunks = [c for c in chunks if c.metadata["chunk_id"] not in manifest]
        skipped = len(chunks) - len(new_chunks)
        if skipped:
            logger.info(f"Incremental: skipped {skipped} existing chunks for user {user_id}.")
        if not new_chunks:
            logger.info("Incremental: all chunks already indexed.")
            return 0
        chunks = new_chunks

    vs = get_vectorstore_for_user(user_id, embeddings=embeddings)
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]

    index_docs: list[Document] = []
    for chunk in chunks:
        enriched_text = build_embedding_text(chunk.page_content, chunk.metadata)
        index_docs.append(
            Document(page_content=enriched_text, metadata=deepcopy(chunk.metadata))
        )
    vs.add_documents(documents=index_docs, ids=ids)

    if use_incremental:
        manifest = _load_manifest(user_id)
        for chunk in chunks:
            manifest[chunk.metadata["chunk_id"]] = chunk.metadata.get("file_name", "unknown")
        _save_manifest(user_id, manifest)

    logger.info(f"Indexed {len(chunks)} chunks for user {user_id} at '{config.chroma_dir}'")
    return len(chunks)


def index_chunks(chunks: List[Document], embeddings=None, incremental: bool | None = None) -> int:
    """Legacy global index — delegates to user_id=0. Kept for CLI compatibility."""
    return index_chunks_for_user(user_id=0, chunks=chunks, embeddings=embeddings, incremental=incremental)


def list_indexed_docs_for_user(user_id: int, embeddings=None) -> List[dict]:
    """Return a list of unique documents in the user's Chroma collection."""
    vs = get_vectorstore_for_user(user_id, embeddings=embeddings)
    collection = vs._collection
    results = collection.get(include=["metadatas"])
    metas = results.get("metadatas", [])

    seen: dict[str, dict] = {}
    for meta in metas:
        fname = meta.get("file_name", "unknown")
        if fname not in seen:
            seen[fname] = {
                "file_name": fname,
                "source": meta.get("source", ""),
                "doc_id": meta.get("doc_id", ""),
                "chunk_count": 0,
            }
        seen[fname]["chunk_count"] += 1

    return list(seen.values())


def list_indexed_docs(embeddings=None) -> List[dict]:
    """Legacy global list — kept for CLI compatibility."""
    return list_indexed_docs_for_user(user_id=0, embeddings=embeddings)
