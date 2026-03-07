"""Summarize endpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from docops.api.schemas import SummarizeRequest, SummarizeResponse
from docops.auth.dependencies import get_current_user
from docops.db.crud import create_artifact_record
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.services.ownership import require_user_document

logger = get_logger("docops.api.summarize")
router = APIRouter()


def _run_summarize(
    file_name: str,
    doc_id: str,
    save: bool,
    summary_mode: str,
    user_id: int,
) -> dict:
    from docops.graph.graph import run
    from docops.tools.doc_tools import tool_write_artifact

    query = (
        f"Faca um resumo breve do documento {file_name}"
        if summary_mode == "brief"
        else f"Faca um resumo aprofundado e detalhado do documento {file_name}"
    )

    state = dict(
        run(
            query=query,
            extra={
                "doc_name": file_name,
                "doc_id": doc_id,
                "summary_mode": summary_mode,
            },
            user_id=user_id,
        )
    )

    artifact_path = None
    artifact_filename = None
    if save:
        answer = state.get("answer", "")
        stem = Path(file_name).stem
        mode_suffix = "breve" if summary_mode == "brief" else "aprofundado"
        filename = f"summary_{mode_suffix}_{stem}.md"
        path = tool_write_artifact(filename, answer, user_id=user_id)
        artifact_path = str(path)
        artifact_filename = path.name

    return {
        "answer": state.get("answer", ""),
        "artifact_path": artifact_path,
        "artifact_filename": artifact_filename,
    }


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(
    body: SummarizeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummarizeResponse:
    """Summarize one document owned by current_user."""
    document = require_user_document(db, current_user.id, body.doc)

    logger.info(
        "Summarize request user=%s doc=%s mode=%s",
        current_user.id,
        document.file_name,
        body.summary_mode,
    )

    try:
        result = await asyncio.to_thread(
            _run_summarize,
            document.file_name,
            document.doc_id,
            body.save,
            body.summary_mode,
            current_user.id,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Summarize error: %s", exc)
        raise HTTPException(status_code=500, detail="Agent error")

    if body.save and result.get("artifact_path") and result.get("artifact_filename"):
        mode_suffix = "breve" if body.summary_mode == "brief" else "aprofundado"
        create_artifact_record(
            db,
            user_id=current_user.id,
            artifact_type="summary",
            title=f"Summary ({mode_suffix}) - {document.file_name}",
            filename=str(result["artifact_filename"]),
            path=str(result["artifact_path"]),
            source_doc_id=document.doc_id,
        )

    return SummarizeResponse(
        answer=str(result.get("answer", "")),
        artifact_path=result.get("artifact_path"),
    )
