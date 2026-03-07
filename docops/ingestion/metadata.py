"""Shared metadata utilities for ingestion/chunking/indexing."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from langchain_core.documents import Document


def _norm_text(text: str) -> str:
    """Normalize text for stable hashing."""
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_source_path(meta: dict[str, Any]) -> str:
    """Return canonical source path from metadata."""
    raw = (
        meta.get("source_path")
        or meta.get("source")
        or meta.get("file_name")
        or "unknown"
    )
    return str(raw).replace("\\", "/")


def infer_file_type(meta: dict[str, Any]) -> str:
    """Infer file type from metadata path/name."""
    existing = str(meta.get("file_type") or "").strip().lower()
    if existing:
        return existing

    probe = str(meta.get("file_name") or meta.get("source_path") or meta.get("source") or "")
    suffix = Path(probe).suffix.lower().lstrip(".")
    return suffix or "unknown"


def _normalize_page_value(value: Any) -> Any:
    if value in (None, "", "None"):
        return "N/A"
    return value


def normalize_pages(meta: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Return (page, page_start, page_end) normalized with N/A fallback."""
    page = _normalize_page_value(meta.get("page"))
    page_start = _normalize_page_value(meta.get("page_start", page))
    page_end = _normalize_page_value(meta.get("page_end", page))
    return page, page_start, page_end


def build_doc_id(source_path: str, user_id: int | None = None) -> str:
    """Stable document id derived from source path + user_id.

    Including user_id ensures two users uploading the same file get
    distinct doc_ids, preventing cross-tenant collisions.
    """
    payload = f"user:{user_id or 0}|{source_path}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_chunk_id(text: str, meta: dict[str, Any]) -> str:
    """Stable chunk id from content + path + page + section + user_id."""
    user_id = meta.get("user_id", 0)
    source_path = normalize_source_path(meta)
    _, page_start, page_end = normalize_pages(meta)
    section_path = str(meta.get("section_path") or "")
    chunk_index = meta.get("chunk_index", "")
    payload = (
        f"user:{user_id}\n"
        f"{source_path}\n"
        f"{page_start}\n"
        f"{page_end}\n"
        f"{section_path}\n"
        f"{chunk_index}\n"
        f"{_norm_text(text)}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_chunk_metadata(
    chunk: Document,
    chunk_index: int,
    stable_ids: bool = True,
    user_id: int | None = None,
) -> None:
    """Normalize chunk metadata in-place to the unified schema."""
    meta = chunk.metadata
    source_path = normalize_source_path(meta)
    file_type = infer_file_type(meta)
    page, page_start, page_end = normalize_pages(meta)
    section_title = str(meta.get("section_title") or "")
    section_path = str(meta.get("section_path") or "")

    effective_user_id = user_id if user_id is not None else meta.get("user_id")
    if effective_user_id is not None:
        meta["user_id"] = int(effective_user_id)

    meta["source_path"] = source_path
    meta["source"] = meta.get("source") or source_path
    meta["storage_path"] = str(meta.get("storage_path") or source_path)
    meta["file_type"] = file_type
    if effective_user_id is not None:
        meta["doc_id"] = build_doc_id(source_path, user_id=int(effective_user_id))
    else:
        meta["doc_id"] = meta.get("doc_id") or build_doc_id(source_path)
    meta["page"] = page
    meta["page_start"] = page_start
    meta["page_end"] = page_end
    meta["section_title"] = section_title
    meta["section_path"] = section_path
    meta["chunk_index"] = int(meta.get("chunk_index", chunk_index))

    if stable_ids:
        meta["chunk_id"] = build_chunk_id(chunk.page_content, meta)
    else:
        # UUID fallback is handled by caller where needed.
        meta.pop("chunk_id", None)


def build_embedding_text(text: str, meta: dict[str, Any]) -> str:
    """Inject section metadata into embedding text for better retrieval."""
    section_path = str(meta.get("section_path") or "")
    section_title = str(meta.get("section_title") or "")
    header_parts: list[str] = []
    if section_path:
        header_parts.append(f"section_path: {section_path}")
    elif section_title:
        header_parts.append(f"section_title: {section_title}")

    page_start = str(meta.get("page_start") or "N/A")
    page_end = str(meta.get("page_end") or "N/A")
    if page_start != "N/A":
        if page_start == page_end:
            header_parts.append(f"page: {page_start}")
        else:
            header_parts.append(f"page_range: {page_start}-{page_end}")

    if not header_parts:
        return text

    header = " | ".join(header_parts)
    return f"[meta] {header}\n{text}"
