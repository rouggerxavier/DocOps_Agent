"""Chat endpoint."""

from __future__ import annotations

import asyncio
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from docops.api.schemas import ChatRequest, ChatResponse, SourceItem
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.db.models import User
from docops.logging import get_logger
from docops.rag.citations import _strip_embedding_header

logger = get_logger("docops.api.chat")
router = APIRouter()


def _extract_sources(state: dict) -> List[SourceItem]:
    """Convert retrieved chunks into response source objects."""
    chunks = state.get("retrieved_chunks") or []
    sources: list[SourceItem] = []

    for idx, doc in enumerate(chunks, start=1):
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


def _run_chat(message: str, top_k: int | None, user_id: int = 0) -> dict:
    from docops.graph.graph import run

    return dict(run(query=message, top_k=top_k, user_id=user_id))


async def _invoke_chat_runner(message: str, top_k: int | None, user_id: int) -> dict:
    """Call _run_chat with compatibility for legacy monkeypatch signatures."""
    try:
        return await asyncio.to_thread(_run_chat, message, top_k, user_id)
    except TypeError:
        return await asyncio.to_thread(_run_chat, message, top_k)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Run chat pipeline with retrieval scoped to current_user."""
    logger.info("Chat request from user %s: '%s'", current_user.id, body.message[:80])

    try:
        state = await _invoke_chat_runner(body.message, body.top_k, current_user.id)
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
