"""Summarize endpoint: POST /api/summarize."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from docops.api.schemas import SummarizeRequest, SummarizeResponse
from docops.logging import get_logger

logger = get_logger("docops.api.summarize")
router = APIRouter()


def _run_summarize(doc: str, save: bool, summary_mode: str) -> dict:
    from docops.graph.graph import run
    from docops.tools.doc_tools import tool_write_artifact
    from pathlib import Path

    query = (
        f"Faça um resumo breve do documento {doc}"
        if summary_mode == "brief"
        else f"Faça um resumo aprofundado e detalhado do documento {doc}"
    )

    state = dict(
        run(
            query=query,
            extra={"doc_name": doc, "summary_mode": summary_mode},
        )
    )

    artifact_path = None
    if save:
        answer = state.get("answer", "")
        stem = Path(doc).stem
        mode_suffix = "breve" if summary_mode == "brief" else "aprofundado"
        path = tool_write_artifact(f"summary_{mode_suffix}_{stem}.md", answer)
        artifact_path = str(path)

    return {"answer": state.get("answer", ""), "artifact_path": artifact_path}


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(body: SummarizeRequest) -> SummarizeResponse:
    """Generate a structured summary for a specific document."""
    logger.info(f"Summarize: {body.doc} (mode={body.summary_mode})")
    try:
        result = await asyncio.to_thread(_run_summarize, body.doc, body.save, body.summary_mode)
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Summarize error: {exc}")
        raise HTTPException(status_code=500, detail="Agent error")

    return SummarizeResponse(**result)
