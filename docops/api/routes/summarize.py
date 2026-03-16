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
    debug_summary: bool = False,
    deep_profile: str | None = None,
) -> dict:
    from docops.tools.doc_tools import tool_write_artifact

    diagnostics = None
    if summary_mode == "deep":
        # Multi-step pipeline: treats the document as a closed, ordered corpus
        from docops.summarize.pipeline import run_deep_summary

        result_dict = run_deep_summary(
            file_name,
            doc_id,
            user_id,
            include_diagnostics=debug_summary,
            profile=deep_profile,
        )
        answer = result_dict.get("answer", "")
        diagnostics = result_dict.get("diagnostics")
    else:
        # Brief mode: existing single-shot graph flow (no regression)
        from docops.graph.graph import run

        state = dict(
            run(
                query=f"Faca um resumo breve do documento {file_name}",
                extra={
                    "doc_name": file_name,
                    "doc_id": doc_id,
                    "summary_mode": "brief",
                },
                user_id=user_id,
            )
        )
        answer = state.get("answer", "")

    artifact_path = None
    artifact_filename = None
    if save:
        stem = Path(file_name).stem
        mode_suffix = "breve" if summary_mode == "brief" else "aprofundado"
        filename = f"summary_{mode_suffix}_{stem}.md"
        path = tool_write_artifact(filename, answer, user_id=user_id)
        artifact_path = str(path)
        artifact_filename = path.name

    return {
        "answer": answer,
        "artifact_path": artifact_path,
        "artifact_filename": artifact_filename,
        "diagnostics": diagnostics,
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
            body.debug_summary,
            body.deep_profile,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Summarize error: %s", exc)
        raise HTTPException(status_code=500, detail="Agent error")

    # Strict fail-closed: em perfil strict, se accepted=False retorna 422
    if body.summary_mode == "deep" and result.get("diagnostics"):
        diag = result["diagnostics"]
        if not diag.get("final", {}).get("accepted", True) and diag.get("profile_used") == "strict":
            blocking = diag.get("final", {}).get("blocking_reasons", [])
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "deep_summary_quality_gate_failed",
                    "blocking_reasons": blocking,
                    "message": (
                        "O resumo aprofundado foi bloqueado pelo gate estrito de qualidade. "
                        "Revise os limiares ou utilize o perfil 'model_first'."
                    ),
                },
            )

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
        artifact_filename=result.get("artifact_filename"),
        summary_diagnostics=result.get("diagnostics") if body.debug_summary else None,
    )
