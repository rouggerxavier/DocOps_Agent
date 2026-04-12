"""Compare endpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from docops.api.schemas import CompareRequest, CompareResponse
from docops.auth.dependencies import get_current_user
from docops.db.crud import create_artifact_record
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.services.ownership import require_user_document

logger = get_logger("docops.api.compare")
router = APIRouter()


def _run_compare(
    doc1_name: str,
    doc1_id: str,
    doc2_name: str,
    doc2_id: str,
    save: bool,
    user_id: int,
) -> dict:
    from docops.graph.graph import run
    from docops.rag.citations import build_context_block
    from docops.rag.retriever import retrieve_for_doc
    from docops.tools.doc_tools import tool_write_artifact

    chunks_doc2 = retrieve_for_doc(
        doc2_name,
        query=f"conteudo principal de {doc2_name}",
        user_id=user_id,
        top_k=200,
        doc_id=doc2_id,
    )
    context_doc2 = build_context_block(chunks_doc2)

    state = dict(
        run(
            query=f"Compare {doc1_name} e {doc2_name}",
            extra={
                "doc1": doc1_name,
                "doc2": doc2_name,
                "doc_name": doc1_name,
                "doc_id": doc1_id,
                "context2": context_doc2,
            },
            user_id=user_id,
        )
    )

    artifact_path = None
    artifact_filename = None
    if save:
        answer = state.get("answer", "")
        stem1 = Path(doc1_name).stem
        stem2 = Path(doc2_name).stem
        filename = f"comparison_{stem1}_vs_{stem2}.md"
        path = tool_write_artifact(filename, answer, user_id=user_id)
        artifact_path = str(path)
        artifact_filename = path.name

    return {
        "answer": state.get("answer", ""),
        "artifact_path": artifact_path,
        "artifact_filename": artifact_filename,
    }


@router.post("/compare", response_model=CompareResponse)
async def compare(
    body: CompareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompareResponse:
    """Compare two documents owned by current_user."""
    doc1 = require_user_document(db, current_user.id, body.doc1)
    doc2 = require_user_document(db, current_user.id, body.doc2)

    logger.info(
        "Compare request user=%s doc1=%s doc2=%s",
        current_user.id,
        doc1.file_name,
        doc2.file_name,
    )

    try:
        result = await asyncio.to_thread(
            _run_compare,
            doc1.file_name,
            doc1.doc_id,
            doc2.file_name,
            doc2.doc_id,
            body.save,
            current_user.id,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Compare error: %s", exc)
        raise HTTPException(status_code=500, detail="Agent error")

    if body.save and result.get("artifact_path") and result.get("artifact_filename"):
        create_artifact_record(
            db,
            user_id=current_user.id,
            artifact_type="comparison",
            title=f"Comparison - {doc1.file_name} vs {doc2.file_name}",
            filename=str(result["artifact_filename"]),
            path=str(result["artifact_path"]),
            generation_profile="comparison:standard",
            source_doc_id=doc1.doc_id,
            source_doc_id_2=doc2.doc_id,
            source_doc_ids=[doc1.doc_id, doc2.doc_id],
        )

    return CompareResponse(
        answer=str(result.get("answer", "")),
        artifact_path=result.get("artifact_path"),
    )
