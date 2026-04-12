"""Summarize endpoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from docops.api.schemas import JobCreateResponse, SummarizeRequest, SummarizeResponse
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.db.crud import create_artifact_record
from docops.db.database import SessionLocal, get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.services.artifact_templates import apply_template_layout, resolve_template
from docops.services.ownership import require_user_document
from docops.services.jobs import create_job, run_thread_with_progress, schedule_job, update_job

logger = get_logger("docops.api.summarize")
router = APIRouter()


def _confidence_level_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _extract_summary_confidence(diagnostics: dict | None) -> tuple[str | None, float | None]:
    if not isinstance(diagnostics, dict):
        return None, None

    score: float | None = None
    coverage = diagnostics.get("coverage", {})
    if isinstance(coverage, dict):
        raw = coverage.get("overall_coverage_score")
        if isinstance(raw, (int, float)):
            score = max(0.0, min(1.0, float(raw)))

    return _confidence_level_from_score(score), score


def _run_summarize(
    file_name: str,
    doc_id: str,
    save: bool,
    summary_mode: str,
    user_id: int,
    template_id: str | None = None,
    debug_summary: bool = False,
    deep_profile: str | None = None,
) -> dict:
    from docops.tools.doc_tools import tool_write_artifact

    template = resolve_template(
        template_id=template_id,
        summary_mode=summary_mode,
        artifact_type="summary",
    )
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
                query=(
                    f"Faca um resumo breve do documento {file_name}. "
                    f"Template obrigatorio: {template.label}. {template.prompt_directive}"
                ),
                extra={
                    "doc_name": file_name,
                    "doc_id": doc_id,
                    "summary_mode": "brief",
                    "template_id": template.template_id,
                },
                user_id=user_id,
            )
        )
        answer = state.get("answer", "")

    mode_label = "Resumo breve" if summary_mode == "brief" else "Resumo aprofundado"
    answer = apply_template_layout(
        answer,
        template=template,
        heading=f"{mode_label} - {Path(file_name).stem}",
        context_line=f"Documento-base: {file_name}",
    )
    confidence_level, confidence_score = _extract_summary_confidence(diagnostics)
    generation_profile = f"summary:{summary_mode}:{template.template_id}"

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
        "template_id": template.template_id,
        "template_label": template.label,
        "template_description": template.short_description,
        "generation_profile": generation_profile,
        "confidence_level": confidence_level,
        "confidence_score": confidence_score,
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
            body.template_id,
            body.debug_summary,
            body.deep_profile,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Summarize error: %s", exc)
        raise HTTPException(status_code=500, detail="Agent error")

    # Strict fail-closed: em perfil strict, accepted=False retorna 422 apenas
    # quando SUMMARY_FAIL_CLOSED_STRICT estiver habilitado.
    if body.summary_mode == "deep" and result.get("diagnostics"):
        diag = result["diagnostics"]
        strict_profile = diag.get("profile_used") == "strict"
        accepted = diag.get("final", {}).get("accepted", True)
        if strict_profile and not accepted and config.summary_fail_closed_strict:
            blocking = diag.get("final", {}).get("blocking_reasons", [])
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "deep_summary_quality_gate_failed",
                    "blocking_reasons": blocking,
                    "message": (
                        "O resumo aprofundado foi bloqueado pelo gate estrito de qualidade. "
                        "Revise os limiares ou utilize os perfis 'balanced' ou 'model_first'."
                    ),
                },
            )
        if strict_profile and not accepted and not config.summary_fail_closed_strict:
            logger.warning(
                "Strict gate reprovou o resumo, mas SUMMARY_FAIL_CLOSED_STRICT=false; retornando resposta."
            )

    if body.save and result.get("artifact_path") and result.get("artifact_filename"):
        mode_suffix = "breve" if body.summary_mode == "brief" else "aprofundado"
        template_label = str(result.get("template_label") or "").strip()
        title_suffix = f" [{template_label}]" if template_label else ""
        create_artifact_record(
            db,
            user_id=current_user.id,
            artifact_type="summary",
            title=f"Summary ({mode_suffix}){title_suffix} - {document.file_name}",
            filename=str(result["artifact_filename"]),
            path=str(result["artifact_path"]),
            template_id=result.get("template_id"),
            generation_profile=result.get("generation_profile"),
            confidence_level=result.get("confidence_level"),
            confidence_score=result.get("confidence_score"),
            source_doc_id=document.doc_id,
            source_doc_ids=[document.doc_id],
        )

    return SummarizeResponse(
        answer=str(result.get("answer", "")),
        artifact_path=result.get("artifact_path"),
        artifact_filename=result.get("artifact_filename"),
        template_id=result.get("template_id"),
        template_label=result.get("template_label"),
        template_description=result.get("template_description"),
        summary_diagnostics=(
            jsonable_encoder(result.get("diagnostics")) if body.debug_summary else None
        ),
    )


@router.post("/summarize/async", response_model=JobCreateResponse)
async def summarize_async(
    body: SummarizeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Create an async summarize job and return a pollable job id."""
    document = require_user_document(db, current_user.id, body.doc)
    job = create_job(user_id=current_user.id, job_type="summarize", stage="queued")

    async def _runner(job_id: str) -> dict:
        update_job(job_id, progress=12, stage="preparing")
        result = await run_thread_with_progress(
            job_id=job_id,
            fn=_run_summarize,
            args=(
                document.file_name,
                document.doc_id,
                body.save,
                body.summary_mode,
                current_user.id,
                body.template_id,
                body.debug_summary,
                body.deep_profile,
            ),
            stage="analyzing document",
            start_progress=30,
            max_progress=82,
            step=5,
            interval_seconds=1.8,
        )
        update_job(job_id, progress=84, stage="persisting")

        if body.save and result.get("artifact_path") and result.get("artifact_filename"):
            mode_suffix = "breve" if body.summary_mode == "brief" else "aprofundado"
            template_label = str(result.get("template_label") or "").strip()
            title_suffix = f" [{template_label}]" if template_label else ""

            def _persist() -> None:
                db_local = SessionLocal()
                try:
                    create_artifact_record(
                        db_local,
                        user_id=current_user.id,
                        artifact_type="summary",
                        title=f"Summary ({mode_suffix}){title_suffix} - {document.file_name}",
                        filename=str(result["artifact_filename"]),
                        path=str(result["artifact_path"]),
                        template_id=result.get("template_id"),
                        generation_profile=result.get("generation_profile"),
                        confidence_level=result.get("confidence_level"),
                        confidence_score=result.get("confidence_score"),
                        source_doc_id=document.doc_id,
                        source_doc_ids=[document.doc_id],
                    )
                finally:
                    db_local.close()

            await asyncio.to_thread(_persist)

        update_job(job_id, progress=100, stage="completed")
        return {
            "answer": str(result.get("answer", "")),
            "artifact_path": result.get("artifact_path"),
            "artifact_filename": result.get("artifact_filename"),
            "template_id": result.get("template_id"),
            "template_label": result.get("template_label"),
            "template_description": result.get("template_description"),
            "summary_diagnostics": (
                jsonable_encoder(result.get("diagnostics")) if body.debug_summary else None
            ),
        }

    schedule_job(job["job_id"], _runner)
    return JobCreateResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=int(job["progress"]),
        stage=str(job["stage"]),
    )
