"""Chat endpoint."""

from __future__ import annotations

import asyncio
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from docops.api.schemas import ChatRequest, ChatResponse, SourceItem
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.rag.citations import _strip_embedding_header
from docops.services.calendar_assistant import maybe_answer_calendar_query
from sqlalchemy.orm import Session

logger = get_logger("docops.api.chat")
router = APIRouter()


_CITATION_RE = re.compile(r"\[Fonte\s*(\d+)\]", re.IGNORECASE)


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
    """Call _run_chat with compatibility for legacy monkeypatch signatures."""
    try:
        return await asyncio.to_thread(
            _run_chat,
            message,
            top_k,
            user_id,
            doc_names,
            strict_grounding,
        )
    except TypeError:
        try:
            return await asyncio.to_thread(_run_chat, message, top_k, user_id, doc_names)
        except TypeError:
            try:
                return await asyncio.to_thread(_run_chat, message, top_k, user_id)
            except TypeError:
                return await asyncio.to_thread(_run_chat, message, top_k)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Run chat pipeline with retrieval scoped to current_user."""
    logger.info("Chat request from user %s: '%s'", current_user.id, body.message[:80])

    from docops.services.orchestrator import maybe_orchestrate
    orch_answer = await asyncio.to_thread(maybe_orchestrate, body.message, current_user.id, db)
    if orch_answer:
        return ChatResponse(
            answer=orch_answer["answer"],
            sources=[],
            intent=orch_answer.get("intent", "action"),
            session_id=body.session_id,
            grounding=None,
        )

    calendar_answer = maybe_answer_calendar_query(body.message, current_user.id, db)
    if calendar_answer:
        return ChatResponse(
            answer=calendar_answer["answer"],
            sources=[],
            intent=calendar_answer.get("intent", "calendar"),
            session_id=body.session_id,
            grounding=None,
            calendar_action=calendar_answer.get("calendar_action"),
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

    return ChatResponse(
        answer=state.get("answer", ""),
        sources=sources,
        intent=state.get("intent", "qa"),
        session_id=body.session_id,
        grounding=grounding_payload if include_grounding else None,
    )
