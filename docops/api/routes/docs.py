"""Docs endpoint: list documents owned by the authenticated user."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from docops.api.schemas import DocItem
from docops.auth.dependencies import get_current_user
from docops.db.crud import list_documents_for_user
from docops.db.database import get_db
from docops.db.models import User

router = APIRouter()


def tool_list_docs(user_id: int, db: Session) -> list[dict]:
    """Return user docs from SQL (source of truth for ownership)."""
    rows = list_documents_for_user(db, user_id)
    return [
        {
            "file_name": row.file_name,
            "source": row.source_path,
            "chunk_count": row.chunk_count,
        }
        for row in rows
    ]


def _safe_tool_list_docs(user_id: int, db: Session) -> list[dict]:
    """Call tool_list_docs with backward-compatible invocation patterns."""
    try:
        return tool_list_docs(user_id, db)
    except TypeError:
        try:
            return tool_list_docs(user_id)  # type: ignore[misc,call-arg]
        except TypeError:
            return tool_list_docs()  # type: ignore[misc,call-arg]


@router.get("/docs", response_model=List[DocItem])
async def list_docs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[DocItem]:
    """List documents for the current user only."""
    rows = _safe_tool_list_docs(current_user.id, db)
    return [
        DocItem(
            file_name=item.get("file_name", ""),
            source=item.get("source", ""),
            chunk_count=int(item.get("chunk_count", 0)),
        )
        for item in rows
    ]
