"""Docs endpoint: list/delete documents owned by the authenticated user."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from docops.api.schemas import DocItem
from docops.auth.dependencies import get_current_user
from docops.db import crud as _crud
from docops.db.crud import list_documents_for_user, get_document_by_user_and_doc_id, delete_document_record
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger

logger = get_logger("docops.api.docs")

router = APIRouter()


def tool_list_docs(user_id: int, db: Session) -> list[dict]:
    """Return user docs from SQL (source of truth for ownership)."""
    rows = list_documents_for_user(db, user_id)
    return [
        {
            "doc_id": row.doc_id,
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
            doc_id=str(item.get("doc_id", "")),
            file_name=item.get("file_name", ""),
            source=item.get("source", ""),
            chunk_count=int(item.get("chunk_count", 0)),
        )
        for item in rows
    ]


@router.delete("/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a document and its vectors — ownership validated."""
    doc = get_document_by_user_and_doc_id(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    # Remove vetores do Chroma + manifest
    try:
        from docops.ingestion.indexer import delete_doc_from_index
        delete_doc_from_index(doc_id=doc_id, user_id=current_user.id)
    except Exception as exc:
        logger.warning("Falha ao remover vetores do Chroma para doc %s: %s", doc_id, exc)

    # Remove arquivo físico de upload (best-effort)
    try:
        from pathlib import Path as _P
        src = _P(doc.source_path) if doc.source_path else None
        if src and src.exists() and src.is_file():
            src.unlink()
    except Exception as exc:
        logger.warning("Falha ao remover arquivo de upload %s: %s", doc.source_path, exc)

    # Remove registro SQL
    delete_document_record(db, current_user.id, doc_id)


# ── Reading status ─────────────────────────────────────────────────────────────

class ReadingStatusUpdate(BaseModel):
    status: str  # to_read | reading | done


@router.get("/docs/reading-status")
async def get_reading_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna mapa {doc_id: status} para todos os docs do usuário."""
    return _crud.get_reading_status_for_user(db, current_user.id)


@router.patch("/docs/{doc_id}/reading-status")
async def update_reading_status(
    doc_id: str,
    body: ReadingStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atualiza o status de leitura de um documento."""
    valid = {"to_read", "reading", "done"}
    if body.status not in valid:
        raise HTTPException(status_code=422, detail=f"Status inválido. Use: {sorted(valid)}")
    doc = get_document_by_user_and_doc_id(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    record = _crud.upsert_reading_status(db, current_user.id, doc_id, body.status)
    return {"doc_id": doc_id, "status": record.status}


# ── File serving ───────────────────────────────────────────────────────────────

from fastapi.responses import FileResponse as _FileResponse
import mimetypes as _mimetypes


@router.get("/docs/{doc_id}/file")
async def get_doc_file(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve o arquivo original do documento para visualização no browser."""
    doc = get_document_by_user_and_doc_id(db, current_user.id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    from pathlib import Path as _P
    src = _P(doc.source_path) if doc.source_path else None
    if not src or not src.exists() or not src.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não disponível no servidor.")

    mime, _ = _mimetypes.guess_type(str(src))
    if not mime:
        mime = "application/octet-stream"

    return _FileResponse(
        path=str(src),
        media_type=mime,
        filename=doc.file_name,
        headers={"Content-Disposition": f'inline; filename="{doc.file_name}"'},
    )
