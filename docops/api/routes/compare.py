"""Compare endpoint: POST /api/compare."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from docops.api.schemas import CompareRequest, CompareResponse
from docops.logging import get_logger

logger = get_logger("docops.api.compare")
router = APIRouter()


def _run_compare(doc1: str, doc2: str, save: bool) -> dict:
    from docops.graph.graph import run
    from docops.rag.retriever import retrieve_for_doc
    from docops.rag.citations import build_context_block
    from docops.tools.doc_tools import tool_write_artifact
    from pathlib import Path

    chunks2 = retrieve_for_doc(doc2, f"conteúdo principal de {doc2}")
    context2 = build_context_block(chunks2)

    state = dict(
        run(
            query=f"Compare {doc1} e {doc2}",
            extra={"doc1": doc1, "doc2": doc2, "context2": context2},
        )
    )

    artifact_path = None
    if save:
        answer = state.get("answer", "")
        stem1 = Path(doc1).stem
        stem2 = Path(doc2).stem
        path = tool_write_artifact(f"comparison_{stem1}_vs_{stem2}.md", answer)
        artifact_path = str(path)

    return {"answer": state.get("answer", ""), "artifact_path": artifact_path}


@router.post("/compare", response_model=CompareResponse)
async def compare(body: CompareRequest) -> CompareResponse:
    """Compare two indexed documents."""
    logger.info(f"Compare: {body.doc1} vs {body.doc2}")
    try:
        result = await asyncio.to_thread(_run_compare, body.doc1, body.doc2, body.save)
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Compare error: {exc}")
        raise HTTPException(status_code=500, detail="Agent error")

    return CompareResponse(**result)
