"""Artifact endpoints: POST /api/artifact, GET /api/artifacts, GET /api/artifacts/{filename}."""

from __future__ import annotations

import asyncio
import mimetypes
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from docops.api.schemas import (
    ArtifactFilterOptionsResponse,
    ArtifactItem,
    ArtifactRequest,
    ArtifactResponse,
    ArtifactTemplateItem,
    ChatArtifactCreateRequest,
    ChatArtifactCreateResponse,
    JobCreateResponse,
)
from docops.auth.dependencies import get_current_user
from docops.config import config  # kept for backward-compatible test patching
from docops.db.crud import (
    create_artifact_record,
    get_artifact_by_user_and_id,
    list_artifact_filter_options_for_user,
    list_artifacts_by_user_and_filename,
    list_artifacts_for_user,
    list_documents_for_user,
    parse_source_doc_ids_blob,
)
from docops.db.database import SessionLocal, get_db
from docops.db.models import ArtifactRecord, User
from docops.logging import get_logger
from docops.observability import emit_event
from docops.services.artifact_templates import apply_template_layout, list_template_payloads, resolve_template
from docops.services.jobs import create_job, run_thread_with_progress, schedule_job, update_job
from docops.services.ownership import require_user_document

logger = get_logger("docops.api.artifact")
router = APIRouter()


def _safe_stem(text: str, limit: int = 48) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    stem = stem.strip("._-") or "artifact"
    return stem[:limit]


def _confidence_level_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _extract_confidence_snapshot(state: dict) -> tuple[str | None, float | None]:
    grounding = state.get("grounding_info") or state.get("grounding") or {}
    if isinstance(grounding, dict):
        raw = grounding.get("support_rate")
        if isinstance(raw, (int, float)):
            score = max(0.0, min(1.0, float(raw)))
            return _confidence_level_from_score(score), score

    quality = state.get("quality_signal")
    if isinstance(quality, dict):
        raw = quality.get("score")
        if isinstance(raw, (int, float)):
            score = max(0.0, min(1.0, float(raw)))
            level = str(quality.get("level") or _confidence_level_from_score(score) or "").strip() or None
            return level, score
    return None, None


def _dedupe_str_values(values: list[str] | None, *, limit: int = 32) -> list[str]:
    if not values:
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
        if len(deduped) >= limit:
            break
    return deduped


def _resolve_chat_doc_context(
    db: Session,
    user_id: int,
    doc_ids: list[str] | None,
    doc_names: list[str] | None,
) -> tuple[list[str], list[str]]:
    clean_doc_ids = _dedupe_str_values(doc_ids)
    clean_doc_names = _dedupe_str_values(doc_names, limit=24)
    docs = list_documents_for_user(db, user_id)
    by_id = {str(doc.doc_id): doc for doc in docs if str(getattr(doc, "doc_id", "")).strip()}
    by_name = {str(doc.file_name).casefold(): doc for doc in docs if str(getattr(doc, "file_name", "")).strip()}

    resolved_ids: list[str] = []
    resolved_names: list[str] = []

    for doc_id in clean_doc_ids:
        matched = by_id.get(doc_id)
        if matched is not None:
            resolved_ids.append(str(matched.doc_id))
            resolved_names.append(str(matched.file_name))

    for doc_name in clean_doc_names:
        matched = by_name.get(doc_name.casefold())
        if matched is not None:
            resolved_ids.append(str(matched.doc_id))
            resolved_names.append(str(matched.file_name))

    final_doc_ids = _dedupe_str_values(clean_doc_ids + resolved_ids, limit=32)
    final_doc_names = _dedupe_str_values(clean_doc_names + resolved_names, limit=24)
    return final_doc_ids, final_doc_names


def _run_artifact(
    type_: str,
    topic: str,
    output: str | None,
    user_id: int,
    template_id: str | None = None,
    doc_names: list[str] | None = None,
    doc_ids: list[str] | None = None,
) -> dict:
    from docops.graph.graph import run
    from docops.tools.doc_tools import tool_write_artifact

    template = resolve_template(
        template_id=template_id,
        artifact_type=type_,
    )
    selected_docs = [name for name in (doc_names or []) if str(name).strip()]
    query = (
        f"Gere um {type_} sobre: {topic}. "
        f"Template obrigatorio: {template.label}. {template.prompt_directive}"
    )
    if selected_docs:
        query += f". Use apenas os documentos: {', '.join(selected_docs)}."

    extra: dict[str, object] = {"topic": topic}
    if selected_docs:
        extra["doc_names"] = selected_docs
    if doc_ids:
        extra["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    extra["template_id"] = template.template_id

    state = dict(
        run(
            query=query,
            extra=extra,
            user_id=user_id,
        )
    )
    confidence_level, confidence_score = _extract_confidence_snapshot(state)
    generation_profile = f"artifact:{type_}:{template.template_id}"
    answer = apply_template_layout(
        state.get("answer", ""),
        template=template,
        heading=f"{type_.replace('_', ' ').title()} - {topic}",
        context_line=(
            f"Tema: {topic}"
            if not selected_docs
            else f"Tema: {topic} | Escopo: {', '.join(selected_docs)}"
        ),
    )
    fname = output or f"{type_}_{_safe_stem(topic)}.md"
    path = tool_write_artifact(fname, answer, user_id=user_id)
    return {
        "answer": answer,
        "filename": path.name,
        "path": str(path),
        "template_id": template.template_id,
        "template_label": template.label,
        "template_description": template.short_description,
        "generation_profile": generation_profile,
        "confidence_level": confidence_level,
        "confidence_score": confidence_score,
    }


@router.get("/artifact/templates", response_model=List[ArtifactTemplateItem])
async def list_artifact_templates(
    summary_mode: str | None = Query(default=None),
    artifact_type: str | None = Query(default=None),
) -> List[ArtifactTemplateItem]:
    payloads = list_template_payloads(summary_mode=summary_mode, artifact_type=artifact_type)
    return [ArtifactTemplateItem(**item) for item in payloads]


def _resolve_artifact_by_id_or_404(db: Session, user_id: int, artifact_id: int) -> ArtifactRecord:
    artifact = get_artifact_by_user_and_id(db, user_id, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artefato nao encontrado.")
    return artifact


def _resolve_artifact_by_filename_or_raise(db: Session, user_id: int, filename: str) -> ArtifactRecord:
    safe_name = Path(filename).name
    matches = list_artifacts_by_user_and_filename(db, user_id, safe_name)
    if not matches:
        raise HTTPException(status_code=404, detail=f"Artifact not found: {safe_name}")
    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "artifact_filename_ambiguous",
                "message": "More than one artifact found with this filename. Use artifact_id.",
                "filename": safe_name,
                "artifact_ids": [item.id for item in matches],
            },
        )
    return matches[0]


def _artifact_file_response(artifact: ArtifactRecord) -> FileResponse:
    artifact_path = Path(artifact.path)
    safe_name = Path(artifact.filename).name

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {safe_name}")

    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return FileResponse(path=str(artifact_path), filename=safe_name, media_type=media_type)


def _delete_artifact_file_best_effort(artifact: ArtifactRecord) -> None:
    try:
        artifact_path = Path(artifact.path)
        if artifact_path.exists() and artifact_path.is_file():
            artifact_path.unlink()
    except Exception as exc:
        logger.warning("Falha ao remover arquivo de artefato %s: %s", artifact.path, exc)


def _artifact_pdf_response(artifact: ArtifactRecord, background_tasks: BackgroundTasks) -> FileResponse:
    import tempfile
    from docops.tools.doc_tools import _markdown_to_pdf

    artifact_path = Path(artifact.path)
    safe_name = Path(artifact.filename).name

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {safe_name}")

    ext = artifact_path.suffix.lower()
    if ext == ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Arquivo ja esta em PDF. Use o download direto do arquivo.",
        )
    if ext not in {".md", ".markdown", ".txt"}:
        raise HTTPException(
            status_code=415,
            detail="Conversao para PDF suporta apenas arquivos .md, .markdown ou .txt.",
        )

    try:
        content = artifact_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = artifact_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = artifact_path.read_text(encoding="cp1252")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="Arquivo de texto invalido para conversao em PDF.",
                )

    pdf_name = Path(safe_name).stem + ".pdf"
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    pdf_path = Path(tmp.name)

    try:
        _markdown_to_pdf(content, pdf_path)
    except Exception as exc:
        import traceback

        logger.error(f"PDF generation error: {exc}\n{traceback.format_exc()}")
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar PDF")

    background_tasks.add_task(pdf_path.unlink, missing_ok=True)
    return FileResponse(
        path=str(pdf_path),
        filename=pdf_name,
        media_type="application/pdf",
        background=background_tasks,
    )


@router.post("/artifact", response_model=ArtifactResponse)
async def create_artifact(
    body: ArtifactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ArtifactResponse:
    """Generate and save a structured artifact scoped to the current user."""
    logger.info(f"Artifact: type={body.type}, topic='{body.topic[:50]}' for user {current_user.id}")
    emit_event(
        logger,
        "artifact.generation.started",
        category="artifact",
        user_id=current_user.id,
        artifact_type=body.type,
        template_id=body.template_id,
        topic_preview=body.topic[:80],
        doc_count=len(body.doc_names or []),
        mode="sync",
    )
    selected_docs = []
    for doc_name in body.doc_names:
        selected_docs.append(require_user_document(db, current_user.id, doc_name))

    doc_names = [doc.file_name for doc in selected_docs]
    doc_ids = [doc.doc_id for doc in selected_docs]

    try:
        result = await asyncio.to_thread(
            _run_artifact,
            body.type,
            body.topic,
            body.output,
            current_user.id,
            body.template_id,
            doc_names,
            doc_ids,
        )
    except EnvironmentError as exc:
        emit_event(
            logger,
            "artifact.generation.failed",
            level="error",
            category="artifact",
            user_id=current_user.id,
            artifact_type=body.type,
            template_id=body.template_id,
            mode="sync",
            error_type=exc.__class__.__name__,
            detail=str(exc),
        )
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Artifact error: {exc}")
        emit_event(
            logger,
            "artifact.generation.failed",
            level="error",
            category="artifact",
            user_id=current_user.id,
            artifact_type=body.type,
            template_id=body.template_id,
            mode="sync",
            error_type=exc.__class__.__name__,
        )
        raise HTTPException(status_code=500, detail="Agent error")

    template_label = str(result.get("template_label") or "").strip()
    title_suffix = f" [{template_label}]" if template_label else ""
    artifact_record = create_artifact_record(
        db,
        user_id=current_user.id,
        artifact_type=body.type,
        title=f"{body.topic[:480]}{title_suffix}"[:512],
        filename=result["filename"],
        path=result["path"],
        template_id=result.get("template_id"),
        generation_profile=result.get("generation_profile"),
        confidence_level=result.get("confidence_level"),
        confidence_score=result.get("confidence_score"),
        source_doc_id=doc_ids[0] if len(doc_ids) >= 1 else None,
        source_doc_id_2=doc_ids[1] if len(doc_ids) >= 2 else None,
        source_doc_ids=doc_ids,
    )
    emit_event(
        logger,
        "artifact.generation.completed",
        category="artifact",
        user_id=current_user.id,
        artifact_type=body.type,
        template_id=result.get("template_id"),
        mode="sync",
        artifact_id=artifact_record.id,
        filename=result["filename"],
    )

    return ArtifactResponse(**result, artifact_id=artifact_record.id)


@router.post("/artifact/from-chat", response_model=ChatArtifactCreateResponse)
async def create_artifact_from_chat(
    body: ChatArtifactCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatArtifactCreateResponse:
    """Persist a chat answer as an artifact with conversation linkage metadata."""
    from docops.features.flags import require_feature_enabled
    from docops.tools.doc_tools import tool_write_artifact

    require_feature_enabled(
        "premium_chat_to_artifact_enabled",
        detail="Chat-to-artifact flow is disabled by feature flag.",
    )

    raw_answer = str(body.answer or "").strip()
    if not raw_answer:
        raise HTTPException(status_code=422, detail="Conteudo do chat vazio para gerar artefato.")

    normalized_doc_ids, normalized_doc_names = _resolve_chat_doc_context(
        db,
        current_user.id,
        body.doc_ids,
        body.doc_names,
    )
    selected_template = resolve_template(
        template_id=body.template_id,
        summary_mode="deep",
        artifact_type="summary",
    )
    base_title = str(body.title or body.user_prompt or "Resumo aprofundado do chat").strip()[:180]
    context_parts = []
    if normalized_doc_names:
        context_parts.append(f"Documentos ativos: {', '.join(normalized_doc_names[:4])}")
    if body.session_id:
        context_parts.append(f"Sessao: {body.session_id}")
    context_line = " | ".join(context_parts) if context_parts else "Origem: conversa em chat"
    final_answer = apply_template_layout(
        raw_answer,
        template=selected_template,
        heading=base_title,
        context_line=context_line,
    )

    turn_suffix = _safe_stem(body.turn_ref or body.session_id or "", limit=20)
    filename = f"chat_summary_{_safe_stem(base_title, limit=40)}{f'_{turn_suffix}' if turn_suffix else ''}.md"
    path = await asyncio.to_thread(
        tool_write_artifact,
        filename,
        final_answer,
        current_user.id,
    )

    confidence_score = body.confidence_score
    if confidence_score is not None:
        confidence_score = max(0.0, min(1.0, float(confidence_score)))
    confidence_level = str(body.confidence_level or "").strip() or _confidence_level_from_score(confidence_score)
    generation_profile = (
        str(body.generation_profile or "").strip()
        or f"chat:deep_summary:{selected_template.template_id}"
    )

    artifact_record = create_artifact_record(
        db,
        user_id=current_user.id,
        artifact_type=str(body.artifact_type or "summary").strip() or "summary",
        title=base_title[:512],
        filename=path.name,
        path=str(path),
        template_id=selected_template.template_id,
        generation_profile=generation_profile,
        confidence_level=confidence_level,
        confidence_score=confidence_score,
        source_doc_id=normalized_doc_ids[0] if len(normalized_doc_ids) >= 1 else None,
        source_doc_id_2=normalized_doc_ids[1] if len(normalized_doc_ids) >= 2 else None,
        source_doc_ids=normalized_doc_ids,
        conversation_session_id=body.session_id,
        conversation_turn_ref=body.turn_ref,
    )

    emit_event(
        logger,
        "artifact.chat_link.created",
        category="artifact",
        user_id=current_user.id,
        artifact_id=artifact_record.id,
        template_id=selected_template.template_id,
        conversation_session_id=body.session_id,
        conversation_turn_ref=body.turn_ref,
        source_doc_count=len(normalized_doc_ids),
    )

    return ChatArtifactCreateResponse(
        answer=final_answer,
        filename=path.name,
        path=str(path),
        template_id=selected_template.template_id,
        template_label=selected_template.label,
        template_description=selected_template.short_description,
        artifact_id=artifact_record.id,
        conversation_session_id=artifact_record.conversation_session_id,
        conversation_turn_ref=artifact_record.conversation_turn_ref,
    )


@router.post("/artifact/async", response_model=JobCreateResponse)
async def create_artifact_async(
    body: ArtifactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """Create an async artifact generation job and return a pollable id."""
    selected_docs = []
    for doc_name in body.doc_names:
        selected_docs.append(require_user_document(db, current_user.id, doc_name))

    doc_names = [doc.file_name for doc in selected_docs]
    doc_ids = [doc.doc_id for doc in selected_docs]
    job = create_job(user_id=current_user.id, job_type="artifact", stage="queued")
    emit_event(
        logger,
        "artifact.generation.started",
        category="artifact",
        user_id=current_user.id,
        artifact_type=body.type,
        template_id=body.template_id,
        topic_preview=body.topic[:80],
        doc_count=len(body.doc_names or []),
        mode="async",
        job_id=job["job_id"],
    )

    async def _runner(job_id: str) -> dict:
        try:
            update_job(job_id, progress=10, stage="collecting context")
            result = await run_thread_with_progress(
                job_id=job_id,
                fn=_run_artifact,
                args=(
                    body.type,
                    body.topic,
                    body.output,
                    current_user.id,
                    body.template_id,
                    doc_names,
                    doc_ids,
                ),
                stage="generating artifact",
                start_progress=28,
                max_progress=82,
                step=4,
                interval_seconds=1.8,
            )
            update_job(job_id, progress=85, stage="saving artifact")

            def _persist() -> None:
                db_local = SessionLocal()
                try:
                    template_label = str(result.get("template_label") or "").strip()
                    title_suffix = f" [{template_label}]" if template_label else ""
                    create_artifact_record(
                        db_local,
                        user_id=current_user.id,
                        artifact_type=body.type,
                        title=f"{body.topic[:480]}{title_suffix}"[:512],
                        filename=result["filename"],
                        path=result["path"],
                        template_id=result.get("template_id"),
                        generation_profile=result.get("generation_profile"),
                        confidence_level=result.get("confidence_level"),
                        confidence_score=result.get("confidence_score"),
                        source_doc_id=doc_ids[0] if len(doc_ids) >= 1 else None,
                        source_doc_id_2=doc_ids[1] if len(doc_ids) >= 2 else None,
                        source_doc_ids=doc_ids,
                    )
                finally:
                    db_local.close()

            await asyncio.to_thread(_persist)
            update_job(job_id, progress=100, stage="completed")
            emit_event(
                logger,
                "artifact.generation.completed",
                category="artifact",
                user_id=current_user.id,
                artifact_type=body.type,
                template_id=result.get("template_id"),
                mode="async",
                job_id=job_id,
                filename=result["filename"],
            )
            return result
        except Exception as exc:
            emit_event(
                logger,
                "artifact.generation.failed",
                level="error",
                category="artifact",
                user_id=current_user.id,
                artifact_type=body.type,
                template_id=body.template_id,
                mode="async",
                job_id=job_id,
                error_type=exc.__class__.__name__,
            )
            raise

    schedule_job(job["job_id"], _runner)
    return JobCreateResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=int(job["progress"]),
        stage=str(job["stage"]),
    )


@router.get("/artifacts", response_model=List[ArtifactItem])
async def list_artifacts(
    artifact_type: str | None = Query(default=None),
    source_doc_id: str | None = Query(default=None),
    conversation_session_id: str | None = Query(default=None),
    template_id: str | None = Query(default=None),
    generation_profile: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ArtifactItem]:
    """List all saved artifacts for the current user (source: SQL)."""
    records = list_artifacts_for_user(
        db,
        current_user.id,
        artifact_type=artifact_type,
        source_doc_id=source_doc_id,
        conversation_session_id=conversation_session_id,
        template_id=template_id,
        generation_profile=generation_profile,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    items = []
    for r in records:
        p = Path(r.path)
        size = p.stat().st_size if p.exists() else 0
        source_doc_ids = []
        for source_id in [r.source_doc_id, r.source_doc_id_2] + parse_source_doc_ids_blob(r.source_doc_ids):
            value = str(source_id or "").strip()
            if value and value not in source_doc_ids:
                source_doc_ids.append(value)
        items.append(
            ArtifactItem(
                id=r.id,
                filename=r.filename,
                size=size,
                created_at=r.created_at.isoformat(),
                artifact_type=r.artifact_type,
                title=r.title,
                template_id=r.template_id,
                generation_profile=r.generation_profile,
                confidence_level=r.confidence_level,
                confidence_score=r.confidence_score,
                metadata_version=int(r.metadata_version or 1),
                source_doc_ids=source_doc_ids,
                source_doc_count=len(source_doc_ids),
                conversation_session_id=r.conversation_session_id,
                conversation_turn_ref=r.conversation_turn_ref,
            )
        )
    return items


@router.get("/artifacts/filters", response_model=ArtifactFilterOptionsResponse)
async def list_artifact_filter_options(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ArtifactFilterOptionsResponse:
    options = list_artifact_filter_options_for_user(db, current_user.id)
    return ArtifactFilterOptionsResponse(**options)


@router.get("/artifacts/id/{artifact_id}")
async def download_artifact_by_id(
    artifact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download artifact by primary id."""
    artifact = _resolve_artifact_by_id_or_404(db, current_user.id, artifact_id)
    return _artifact_file_response(artifact)


@router.delete("/artifacts/id/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact_by_id(
    artifact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete artifact by primary id."""
    artifact = _resolve_artifact_by_id_or_404(db, current_user.id, artifact_id)
    _delete_artifact_file_best_effort(artifact)
    db.delete(artifact)
    db.commit()


@router.get("/artifacts/id/{artifact_id}/pdf")
async def download_artifact_pdf_by_id(
    artifact_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Convert/download artifact as PDF by primary id."""
    artifact = _resolve_artifact_by_id_or_404(db, current_user.id, artifact_id)
    return _artifact_pdf_response(artifact, background_tasks)


@router.get("/artifacts/{filename}")
async def download_artifact(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Legacy filename route, fails with 409 when filename is ambiguous."""
    artifact = _resolve_artifact_by_filename_or_raise(db, current_user.id, filename)
    return _artifact_file_response(artifact)


@router.delete("/artifacts/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Legacy filename route, fails with 409 when filename is ambiguous."""
    artifact = _resolve_artifact_by_filename_or_raise(db, current_user.id, filename)
    _delete_artifact_file_best_effort(artifact)
    db.delete(artifact)
    db.commit()


@router.get("/artifacts/{filename}/pdf")
async def download_artifact_pdf(
    filename: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Legacy filename route, fails with 409 when filename is ambiguous."""
    artifact = _resolve_artifact_by_filename_or_raise(db, current_user.id, filename)
    return _artifact_pdf_response(artifact, background_tasks)
