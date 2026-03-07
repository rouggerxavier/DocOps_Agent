"""User-scoped filesystem paths for multi-tenant isolation.

All user-specific data (uploads, artifacts, BM25 indices) is stored
in per-user directories derived from the user's database ID.
"""

from __future__ import annotations

from pathlib import Path

from docops.config import config


def _ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it does not exist, then return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_upload_dir(user_id: int) -> Path:
    """Return (and create) the upload directory for a user."""
    base = getattr(config, "uploads_dir", None)
    if not isinstance(base, Path):
        base = config.docs_dir
    return _ensure_dir(base / f"user_{user_id}")


def get_user_artifacts_dir(user_id: int) -> Path:
    """Return (and create) the artifacts directory for a user."""
    return _ensure_dir(config.artifacts_dir / f"user_{user_id}")


def get_user_bm25_dir(user_id: int) -> Path:
    """Return (and create) the BM25 index directory for a user."""
    return _ensure_dir(config.bm25_dir / f"user_{user_id}")


def get_user_collection_name(user_id: int) -> str:
    """Return the Chroma collection name scoped to a user."""
    return f"docops_user_{user_id}"
