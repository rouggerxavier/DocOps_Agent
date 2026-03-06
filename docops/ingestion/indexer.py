"""Indexer: persists document chunks into a Chroma vector store.

The store is saved at CHROMA_DIR (env var, default ./data/chroma).
Google Generative AI Embeddings are used via GEMINI_API_KEY.

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

def get_vectorstore(embeddings=None):
    """Return (or open) the persistent Chroma vector store.

    Args:
        embeddings: Optional embedding function. Defaults to Google GenAI embeddings.
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

def _manifest_path() -> Path:
    return config.chroma_dir / "ingest_manifest.json"


def _load_manifest() -> dict:
    """Load the ingestion manifest (chunk_id → file_name mapping)."""
    p = _manifest_path()
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(manifest: dict) -> None:
    """Persist the ingestion manifest."""
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def index_chunks(chunks: List[Document], embeddings=None, incremental: bool | None = None) -> int:
    """Add chunks to the Chroma vector store and return count of indexed chunks.

    When incremental mode is enabled, chunks whose IDs already exist in the
    manifest are skipped (upsert semantics). This avoids re-embedding
    unchanged content.

    Args:
        chunks: List of Document objects with metadata (chunk_id, file_name, etc.).
        embeddings: Optional embedding function override (useful for tests).
        incremental: Override incremental mode. Defaults to config.ingest_incremental.
    """
    if not chunks:
        logger.warning("No chunks to index.")
        return 0

    use_incremental = incremental if incremental is not None else config.ingest_incremental

    # Normalize schema before any persistence checks so IDs and metadata are stable.
    normalized_chunks: list[Document] = []
    for i, chunk in enumerate(chunks):
        cloned = Document(
            page_content=chunk.page_content,
            metadata=deepcopy(chunk.metadata),
        )
        normalize_chunk_metadata(cloned, chunk_index=i, stable_ids=True)
        normalized_chunks.append(cloned)
    chunks = normalized_chunks

    if use_incremental:
        manifest = _load_manifest()
        new_chunks = [c for c in chunks if c.metadata["chunk_id"] not in manifest]
        skipped = len(chunks) - len(new_chunks)
        if skipped:
            logger.info(f"Incremental: skipped {skipped} existing chunks.")
        if not new_chunks:
            logger.info("Incremental: all chunks already indexed.")
            return 0
        chunks = new_chunks

    vs = get_vectorstore(embeddings=embeddings)
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]

    # Include section metadata in indexed text so embeddings capture structure.
    index_docs: list[Document] = []
    for chunk in chunks:
        enriched_text = build_embedding_text(chunk.page_content, chunk.metadata)
        index_docs.append(
            Document(page_content=enriched_text, metadata=deepcopy(chunk.metadata))
        )
    vs.add_documents(documents=index_docs, ids=ids)

    if use_incremental:
        manifest = _load_manifest()
        for chunk in chunks:
            manifest[chunk.metadata["chunk_id"]] = chunk.metadata.get("file_name", "unknown")
        _save_manifest(manifest)

    logger.info(f"Indexed {len(chunks)} chunks into Chroma at '{config.chroma_dir}'")
    return len(chunks)


def list_indexed_docs(embeddings=None) -> List[dict]:
    """Return a list of unique documents currently in the Chroma vector store.

    Args:
        embeddings: Optional embedding function override (useful for tests).
    """
    vs = get_vectorstore(embeddings=embeddings)
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
                "chunk_count": 0,
            }
        seen[fname]["chunk_count"] += 1

    return list(seen.values())
