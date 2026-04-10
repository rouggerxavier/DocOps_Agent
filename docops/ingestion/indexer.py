"""Indexer: persists document chunks into per-user Chroma vector store collections.

Each user gets their own Chroma collection (docops_user_<id>),
ensuring complete data isolation at the vector store level.

Supports incremental ingestion: when INGEST_INCREMENTAL=true, existing
documents are compared by doc_id and unchanged documents can be skipped.
For reingest, previous chunks for the same doc_id are replaced to avoid
stale vector/BM25 state.
"""

import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from docops.config import config
from docops.ingestion.metadata import build_embedding_text, normalize_chunk_metadata
from docops.logging import get_logger
from docops.storage.paths import get_user_collection_name

logger = get_logger("docops.ingestion.indexer")


def _ensure_sqlite_compat() -> None:
    """Ensure sqlite3 is compatible with Chroma on older Linux distros.

    Ubuntu 20.04 ships sqlite3 < 3.35, which is unsupported by Chroma.
    When needed, swap stdlib sqlite3 with pysqlite3-binary at runtime.
    """
    if sqlite3.sqlite_version_info >= (3, 35, 0):
        return

    try:
        import pysqlite3
    except Exception as exc:  # pragma: no cover - exercised only in old sqlite envs
        raise RuntimeError(
            "SQLite too old for Chroma (need >= 3.35). Install pysqlite3-binary "
            "or use a runtime with newer sqlite."
        ) from exc

    sys.modules["sqlite3"] = pysqlite3


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

    _ensure_sqlite_compat()
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
    _ensure_sqlite_compat()
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


def _normalize_id_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item)]


def _remove_chunk_ids_from_manifest(user_id: int, chunk_ids: set[str]) -> None:
    if not chunk_ids:
        return
    manifest = _load_manifest(user_id)
    if not manifest:
        return
    before = len(manifest)
    filtered = {k: v for k, v in manifest.items() if k not in chunk_ids}
    if len(filtered) != before:
        _save_manifest(user_id, filtered)


def _strip_embedding_meta_header(text: str) -> str:
    if text.startswith("[meta] ") and "\n" in text:
        return text.split("\n", 1)[1]
    return text


def _sync_bm25_from_vectorstore_for_user(user_id: int, embeddings=None) -> None:
    """Rebuild BM25 corpus from the authoritative vectorstore state."""
    if user_id <= 0:
        return

    from docops.rag.hybrid import build_bm25_index_for_user

    vs = get_vectorstore_for_user(user_id, embeddings=embeddings)
    collection = getattr(vs, "_collection", None)
    if collection is None:
        logger.warning("Unable to sync BM25 for user %s: vectorstore collection unavailable.", user_id)
        return

    try:
        raw = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("Unable to read vectorstore for BM25 sync (user=%s): %s", user_id, exc)
        return

    if not isinstance(raw, dict):
        logger.warning("Unexpected vectorstore payload while syncing BM25 for user %s.", user_id)
        return

    documents = raw.get("documents", [])
    metadatas = raw.get("metadatas", [])
    if not isinstance(documents, list):
        documents = []
    if not isinstance(metadatas, list):
        metadatas = []

    chunks: list[Document] = []
    for idx, text in enumerate(documents):
        if not isinstance(text, str):
            continue
        meta = metadatas[idx] if idx < len(metadatas) and isinstance(metadatas[idx], dict) else {}
        chunks.append(
            Document(
                page_content=_strip_embedding_meta_header(text),
                metadata=deepcopy(meta),
            )
        )

    build_bm25_index_for_user(user_id=user_id, chunks=chunks)


def _replace_doc_chunks_in_collection(
    *,
    user_id: int,
    chunks: list[Document],
    collection,
    use_incremental: bool,
) -> list[Document]:
    """Replace existing chunks per doc_id to prevent stale vectors on reingest."""
    grouped: dict[str, list[Document]] = {}
    for chunk in chunks:
        doc_id = str(chunk.metadata.get("doc_id") or "").strip()
        grouped.setdefault(doc_id, []).append(chunk)

    kept_chunks: list[Document] = []
    removed_ids: set[str] = set()

    for doc_id, doc_chunks in grouped.items():
        if not doc_id:
            kept_chunks.extend(doc_chunks)
            continue

        existing_ids: set[str] = set()
        try:
            payload = collection.get(where={"doc_id": doc_id}, include=[])
            if isinstance(payload, dict):
                existing_ids = set(_normalize_id_list(payload.get("ids", [])))
        except Exception as exc:
            logger.warning("Could not inspect existing chunks for doc_id=%s (user=%s): %s", doc_id, user_id, exc)

        incoming_ids = {
            str(c.metadata.get("chunk_id") or "")
            for c in doc_chunks
            if str(c.metadata.get("chunk_id") or "")
        }
        unchanged = use_incremental and bool(existing_ids) and existing_ids == incoming_ids
        if unchanged:
            logger.info(
                "Incremental: doc_id=%s unchanged for user %s, skipping reindex.",
                doc_id,
                user_id,
            )
            continue

        if existing_ids:
            try:
                collection.delete(ids=list(existing_ids))
                removed_ids.update(existing_ids)
                logger.info(
                    "Reingest replace: removed %d stale chunks for doc_id=%s (user=%s).",
                    len(existing_ids),
                    doc_id,
                    user_id,
                )
            except Exception as exc:
                logger.warning("Failed to delete stale chunks for doc_id=%s (user=%s): %s", doc_id, user_id, exc)

        kept_chunks.extend(doc_chunks)

    _remove_chunk_ids_from_manifest(user_id, removed_ids)
    return kept_chunks


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

    vs = get_vectorstore_for_user(user_id, embeddings=embeddings)
    collection = getattr(vs, "_collection", None)

    if user_id > 0 and collection is not None:
        chunks = _replace_doc_chunks_in_collection(
            user_id=user_id,
            chunks=chunks,
            collection=collection,
            use_incremental=use_incremental,
        )
        if not chunks:
            _sync_bm25_from_vectorstore_for_user(user_id, embeddings=embeddings)
            return 0
    elif use_incremental:
        # Legacy fallback path (user_id=0 and mock-based tests).
        manifest = _load_manifest(user_id)
        new_chunks = [c for c in chunks if c.metadata["chunk_id"] not in manifest]
        skipped = len(chunks) - len(new_chunks)
        if skipped:
            logger.info(f"Incremental: skipped {skipped} existing chunks for user {user_id}.")
        if not new_chunks:
            logger.info("Incremental: all chunks already indexed.")
            return 0
        chunks = new_chunks

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

    _sync_bm25_from_vectorstore_for_user(user_id, embeddings=embeddings)

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


def delete_doc_from_index(doc_id: str, user_id: int, embeddings=None) -> int:
    """Remove all chunks for a given doc_id from the user's Chroma collection.

    Returns the number of chunks deleted.
    """
    vs = get_vectorstore_for_user(user_id, embeddings=embeddings)
    collection = vs._collection

    # Find IDs matching this doc_id
    results = collection.get(where={"doc_id": doc_id}, include=[])
    ids_to_delete = _normalize_id_list(results.get("ids", []) if isinstance(results, dict) else [])

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        logger.info("Removidos %d chunks do Chroma para doc_id=%s user=%s", len(ids_to_delete), doc_id, user_id)

    _remove_chunk_ids_from_manifest(user_id, set(ids_to_delete))
    _sync_bm25_from_vectorstore_for_user(user_id, embeddings=embeddings)

    return len(ids_to_delete)
