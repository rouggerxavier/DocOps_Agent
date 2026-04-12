"""Chat endpoint."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from docops.api.schemas import ChatQualitySignal, ChatRequest, ChatResponse, SourceItem
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.db.database import get_db, session_scope
from docops.db.models import User
from docops.logging import get_logger
from docops.rag.citations import _strip_embedding_header
from docops.services.calendar_assistant import maybe_answer_calendar_query
from docops.services.chat_context import (
    get_active_context,
    merge_active_context,
    normalize_active_context,
    remember_active_context,
)
from sqlalchemy.orm import Session

logger = get_logger("docops.api.chat")
router = APIRouter()


_CITATION_RE = re.compile(r"\[Fonte\s*(\d+)\]", re.IGNORECASE)
_STREAM_CHARS_PER_CHUNK = 1
_STREAM_DELAY_SECONDS = 0.01


def _extract_cited_indices(answer: str, total_chunks: int) -> list[int]:
    """Return valid [Fonte N] indices found in answer, preserving first-seen order."""
    if total_chunks <= 0 or not answer:
        return []

    seen: set[int] = set()
    ordered: list[int] = []
    for match in _CITATION_RE.finditer(answer):
        idx = int(match.group(1))
        if idx < 1 or idx > total_chunks or idx in seen:
            continue
        seen.add(idx)
        ordered.append(idx)
    return ordered


def _extract_sources(state: dict) -> List[SourceItem]:
    """Convert retrieved chunks into response source objects.

    Prefer only sources that were actually cited in the answer body.
    Fallback to all retrieved chunks when no valid citation is present.
    """
    chunks = state.get("retrieved_chunks") or []
    answer = str(state.get("answer", "") or "")
    cited_indices = _extract_cited_indices(answer, len(chunks))
    selected_indices = cited_indices if cited_indices else list(range(1, len(chunks) + 1))

    sources: list[SourceItem] = []

    for idx in selected_indices:
        doc = chunks[idx - 1]
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        text = doc.page_content if hasattr(doc, "page_content") else str(doc)
        text = _strip_embedding_header(text)
        snippet = re.sub(r"\s+", " ", text[:200]).strip()

        sources.append(
            SourceItem(
                fonte_n=idx,
                file_name=metadata.get("file_name", ""),
                page=str(metadata.get("page", "N/A")),
                section_path=str(
                    metadata.get("section_path", "") or metadata.get("section_title", "")
                ),
                snippet=snippet,
                chunk_id=metadata.get("chunk_id", ""),
            )
        )

    return sources


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_quality_signal(state: dict, sources: list[SourceItem]) -> ChatQualitySignal:
    """Compute a lightweight confidence signal for chat UX."""
    retrieved_chunks = state.get("retrieved_chunks") or []
    retrieved_count = len(retrieved_chunks)
    source_count = len(sources)

    grounding = state.get("grounding") or state.get("grounding_info") or {}
    support_rate = _as_float(grounding.get("support_rate"))
    unsupported_claims = grounding.get("unsupported_claims") or []
    unsupported_count = len(unsupported_claims) if isinstance(unsupported_claims, list) else 0

    score = support_rate if support_rate is not None else 0.55
    reasons: list[str] = []

    if support_rate is not None:
        reasons.append(f"support_rate={support_rate:.2f}")
    if source_count == 0:
        reasons.append("no_inline_sources")
        score -= 0.25
    elif source_count == 1:
        reasons.append("single_source")
        score -= 0.08
    else:
        reasons.append("multi_source")
        score += 0.08
    if retrieved_count == 0:
        reasons.append("no_retrieval")
        score -= 0.35
    if unsupported_count > 0:
        reasons.append(f"unsupported_claims={unsupported_count}")
        score -= min(0.3, unsupported_count * 0.05)

    score = max(0.0, min(1.0, round(score, 2)))

    if score >= 0.8:
        level = "high"
        label = "Alta confiabilidade"
    elif score >= 0.55:
        level = "medium"
        label = "Confiabilidade moderada"
    else:
        level = "low"
        label = "Baixa confiabilidade"

    suggested_action: str | None = None
    if level == "low":
        if retrieved_count == 0:
            suggested_action = (
                "Nao encontrei evidencias nos documentos atuais. "
                "Considere ingerir mais material sobre este tema."
            )
        elif source_count == 0:
            suggested_action = (
                "Tente pedir uma resposta com citacoes explicitas "
                "(por exemplo: inclua [Fonte N] no texto)."
            )
        else:
            suggested_action = (
                "A resposta tem suporte parcial. Vale reformular a pergunta "
                "ou ampliar o conjunto de documentos."
            )

    return ChatQualitySignal(
        level=level,
        score=score,
        label=label,
        reasons=reasons,
        suggested_action=suggested_action,
        source_count=source_count,
        retrieved_count=retrieved_count,
    )


def _run_chat(
    message: str,
    top_k: int | None,
    user_id: int = 0,
    doc_names: list[str] | None = None,
    strict_grounding: bool = False,
) -> dict:
    from docops.graph.graph import run

    extra = {}
    if doc_names:
        clean_doc_names = [str(name).strip() for name in doc_names if str(name).strip()]
        if clean_doc_names:
            extra["doc_names"] = clean_doc_names
    if strict_grounding:
        extra["strict_grounding"] = True

    return dict(run(query=message, top_k=top_k, user_id=user_id, extra=extra or None))


async def _invoke_chat_runner(
    message: str,
    top_k: int | None,
    user_id: int,
    doc_names: list[str] | None = None,
    strict_grounding: bool = False,
) -> dict:
    """Run chat inference in a worker thread with the canonical signature."""
    return await asyncio.to_thread(
        _run_chat,
        message,
        top_k,
        user_id,
        doc_names,
        strict_grounding,
    )


async def _invoke_orchestrator(
    message: str,
    user_id: int,
    db: Session,
    history: list[dict] | None = None,
    session_id: str | None = None,
    active_context: dict | None = None,
) -> dict | None:
    """Run orchestrator logic in a worker thread using a local DB session."""
    from docops.services.orchestrator import maybe_orchestrate

    def _run_with_local_session() -> dict | None:
        db_bind = db.get_bind()
        with session_scope(bind=db_bind) as db_local:
            return maybe_orchestrate(
                message,
                user_id,
                db_local,
                history,
                session_id,
                active_context,
            )

    return await asyncio.to_thread(_run_with_local_session)


def _resolve_doc_context(doc_refs: list[str], user_id: int, db: Session) -> dict:
    if not doc_refs:
        return normalize_active_context(None)

    refs = {str(ref).strip() for ref in doc_refs if str(ref).strip()}
    if not refs:
        return normalize_active_context(None)

    try:
        from docops.db import crud

        docs = crud.list_documents_for_user(db, user_id)
    except Exception:
        docs = []

    matched_ids: list[str] = []
    matched_names: list[str] = []
    lowered_refs = {ref.casefold() for ref in refs}
    for doc in docs:
        doc_id = str(getattr(doc, "doc_id", "") or "").strip()
        file_name = str(getattr(doc, "file_name", "") or "").strip()
        if doc_id in refs or file_name in refs or file_name.casefold() in lowered_refs:
            if doc_id:
                matched_ids.append(doc_id)
            if file_name:
                matched_names.append(file_name)

    return normalize_active_context(
        {
            "active_doc_ids": matched_ids,
            "active_doc_names": matched_names,
        }
    )


def _derive_rag_context(
    message: str,
    intent: str,
    selected_doc_context: dict,
    sources: list[SourceItem],
) -> dict:
    patch = {
        "active_intent": intent,
        "last_action": "rag_answer",
        "last_user_command": message,
    }
    if selected_doc_context.get("active_doc_names"):
        patch["active_doc_names"] = selected_doc_context.get("active_doc_names")
        patch["active_doc_ids"] = selected_doc_context.get("active_doc_ids")
        return patch

    source_names = list(dict.fromkeys(source.file_name for source in sources if source.file_name))[:5]
    if source_names:
        patch["active_doc_names"] = source_names
    return patch


def _derive_calendar_context(message: str, calendar_answer: dict) -> dict:
    calendar_action = calendar_answer.get("calendar_action") or {}
    title = calendar_action.get("title") or calendar_action.get("schedule_title")
    patch = {
        "active_intent": calendar_answer.get("intent", "calendar"),
        "last_action": calendar_answer.get("intent", "calendar"),
        "last_user_command": message,
    }
    if title:
        patch["active_task_title"] = str(title)
    return patch


async def _build_chat_response(
    body: ChatRequest,
    current_user: User,
    db: Session,
) -> ChatResponse:
    """Run chat pipeline with retrieval scoped to current_user."""
    # Converte history do schema para lista de dicts simples
    history = [{"role": m.role, "content": m.content} for m in (body.history or [])]
    stored_context = get_active_context(current_user.id, body.session_id)
    request_context = normalize_active_context(
        body.active_context.model_dump() if body.active_context else None
    )
    selected_doc_context = _resolve_doc_context(body.doc_names, current_user.id, db)
    active_context = merge_active_context(
        request_context if body.active_context is not None else stored_context,
        selected_doc_context,
    )

    orch_answer = await _invoke_orchestrator(
        body.message,
        current_user.id,
        db,
        history,
        body.session_id,
        active_context,
    )
    if orch_answer:
        next_context = remember_active_context(
            current_user.id,
            body.session_id,
            merge_active_context(
                active_context,
                {
                    **(orch_answer.get("active_context") or {}),
                    "last_user_command": body.message,
                    "active_intent": orch_answer.get("intent", "action"),
                },
            ),
        )
        return ChatResponse(
            answer=orch_answer["answer"],
            sources=[],
            intent=orch_answer.get("intent", "action"),
            session_id=body.session_id,
            grounding=None,
            action_metadata=orch_answer.get("action_metadata"),
            needs_confirmation=bool(orch_answer.get("needs_confirmation", False)),
            confirmation_text=orch_answer.get("confirmation_text"),
            suggested_reply=orch_answer.get("suggested_reply"),
            active_context=next_context,
        )

    calendar_answer = maybe_answer_calendar_query(body.message, current_user.id, db, history=history)
    if calendar_answer:
        next_context = remember_active_context(
            current_user.id,
            body.session_id,
            merge_active_context(active_context, _derive_calendar_context(body.message, calendar_answer)),
        )
        return ChatResponse(
            answer=calendar_answer["answer"],
            sources=[],
            intent=calendar_answer.get("intent", "calendar"),
            session_id=body.session_id,
            grounding=None,
            calendar_action=calendar_answer.get("calendar_action"),
            action_metadata=calendar_answer.get("action_metadata"),
            needs_confirmation=bool(calendar_answer.get("needs_confirmation", False)),
            confirmation_text=calendar_answer.get("confirmation_text"),
            suggested_reply=calendar_answer.get("suggested_reply"),
            active_context=next_context,
        )

    try:
        state = await _invoke_chat_runner(
            body.message,
            body.top_k,
            current_user.id,
            body.doc_names,
            body.strict_grounding,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        raise HTTPException(status_code=500, detail="Agent error - check server logs")

    sources = _extract_sources(state)
    include_grounding = body.debug_grounding or config.debug_grounding
    grounding_payload = state.get("grounding") or state.get("grounding_info")
    quality_signal = _build_quality_signal(state, sources)
    logger.info(
        "Chat quality signal user=%s intent=%s level=%s score=%.2f reasons=%s",
        current_user.id,
        state.get("intent", "qa"),
        quality_signal.level,
        quality_signal.score,
        ",".join(quality_signal.reasons),
    )
    next_context = remember_active_context(
        current_user.id,
        body.session_id,
        merge_active_context(
            active_context,
            merge_active_context(
                state.get("active_context"),
                _derive_rag_context(body.message, state.get("intent", "qa"), selected_doc_context, sources),
            ),
        ),
    )

    return ChatResponse(
        answer=state.get("answer", ""),
        sources=sources,
        intent=state.get("intent", "qa"),
        session_id=body.session_id,
        grounding=grounding_payload if include_grounding else None,
        action_metadata=state.get("action_metadata"),
        needs_confirmation=bool(state.get("needs_confirmation", False)),
        confirmation_text=state.get("confirmation_text"),
        suggested_reply=state.get("suggested_reply"),
        active_context=next_context,
        quality_signal=quality_signal,
    )


def _sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    logger.info("Chat request from user %s: '%s'", current_user.id, body.message[:80])
    return await _build_chat_response(body, current_user, db)


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream chat answer incrementally as SSE events."""
    logger.info("Chat stream request from user %s: '%s'", current_user.id, body.message[:80])

    async def event_generator():
        yield _sse_payload({"type": "start", "session_id": body.session_id})

        try:
            response = await _build_chat_response(body, current_user, db)
        except HTTPException as exc:
            yield _sse_payload(
                {
                    "type": "error",
                    "status_code": exc.status_code,
                    "detail": str(exc.detail),
                }
            )
            return
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.error("Chat stream error: %s", exc)
            yield _sse_payload(
                {
                    "type": "error",
                    "status_code": 500,
                    "detail": "Agent error - check server logs",
                }
            )
            return

        answer = response.answer or ""
        for idx in range(0, len(answer), _STREAM_CHARS_PER_CHUNK):
            chunk = answer[idx : idx + _STREAM_CHARS_PER_CHUNK]
            if chunk:
                yield _sse_payload({"type": "delta", "delta": chunk})
                await asyncio.sleep(_STREAM_DELAY_SECONDS)

        yield _sse_payload({"type": "final", "response": response.model_dump(mode="json")})
        yield _sse_payload({"type": "done"})

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
