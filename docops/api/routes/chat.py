"""Chat endpoint: POST /api/chat."""

from __future__ import annotations

import asyncio
import re
from typing import List

from fastapi import APIRouter, HTTPException

from docops.api.schemas import ChatRequest, ChatResponse, SourceItem
from docops.config import config
from docops.logging import get_logger
from docops.rag.citations import _strip_embedding_header

logger = get_logger("docops.api.chat")
router = APIRouter()


def _extract_sources(state: dict) -> List[SourceItem]:
    """Convert retrieved_chunks from AgentState to structured SourceItem list."""
    chunks = state.get("retrieved_chunks") or []
    sources = []
    for i, doc in enumerate(chunks, start=1):
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        text = doc.page_content if hasattr(doc, "page_content") else str(doc)
        text = _strip_embedding_header(text)
        # Build snippet: first 200 chars, strip newlines
        snippet = re.sub(r"\s+", " ", text[:200]).strip()
        sources.append(
            SourceItem(
                fonte_n=i,
                file_name=meta.get("file_name", ""),
                page=str(meta.get("page", "N/A")),
                section_path=str(meta.get("section_path", "") or meta.get("section_title", "")),
                snippet=snippet,
                chunk_id=meta.get("chunk_id", ""),
            )
        )
    return sources


def _run_chat(message: str, top_k: int | None) -> dict:
    from docops.graph.graph import run
    return dict(run(query=message, top_k=top_k))


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Send a message to the agent and receive an answer with cited sources."""
    logger.info(f"Chat request: '{body.message[:80]}'")

    try:
        state = await asyncio.to_thread(_run_chat, body.message, body.top_k)
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Chat error: {exc}")
        raise HTTPException(status_code=500, detail="Agent error — check server logs")

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
