"""Artifact endpoints: POST /api/artifact, GET /api/artifacts, GET /api/artifacts/{filename}."""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from docops.api.schemas import ArtifactItem, ArtifactRequest, ArtifactResponse
from docops.config import config
from docops.logging import get_logger

logger = get_logger("docops.api.artifact")
router = APIRouter()


def _run_artifact(type_: str, topic: str, output: str | None) -> dict:
    from docops.graph.graph import run
    from docops.tools.doc_tools import tool_write_artifact

    state = dict(
        run(
            query=f"Gere um {type_} sobre: {topic}",
            extra={"topic": topic},
        )
    )
    answer = state.get("answer", "")
    fname = output or f"{type_}_{topic[:30].replace(' ', '_')}.md"
    path = tool_write_artifact(fname, answer)
    return {"answer": answer, "filename": path.name, "path": str(path)}


@router.post("/artifact", response_model=ArtifactResponse)
async def create_artifact(body: ArtifactRequest) -> ArtifactResponse:
    """Generate and save a structured artifact (study plan, checklist, etc.)."""
    logger.info(f"Artifact: type={body.type}, topic='{body.topic[:50]}'")
    try:
        result = await asyncio.to_thread(
            _run_artifact, body.type, body.topic, body.output
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Artifact error: {exc}")
        raise HTTPException(status_code=500, detail="Agent error")

    return ArtifactResponse(**result)


@router.get("/artifacts", response_model=List[ArtifactItem])
async def list_artifacts() -> List[ArtifactItem]:
    """List all saved artifacts."""
    artifacts_dir = config.artifacts_dir
    if not artifacts_dir.exists():
        return []

    items = []
    for f in sorted(artifacts_dir.iterdir()):
        if f.is_file():
            stat = f.stat()
            items.append(
                ArtifactItem(
                    filename=f.name,
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                )
            )
    return items


@router.get("/artifacts/{filename}")
async def download_artifact(filename: str) -> FileResponse:
    """Download a specific artifact file."""
    # Sanitize — no path traversal
    safe_name = Path(filename).name
    artifact_path = config.artifacts_dir / safe_name

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {filename}")

    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    return FileResponse(
        path=str(artifact_path),
        filename=safe_name,
        media_type=media_type,
    )


@router.get("/artifacts/{filename}/pdf")
async def download_artifact_pdf(filename: str) -> FileResponse:
    """Convert a Markdown artifact to PDF and return it for download."""
    import tempfile
    from docops.tools.doc_tools import _markdown_to_pdf

    safe_name = Path(filename).name
    artifact_path = config.artifacts_dir / safe_name

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {filename}")

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
        raise HTTPException(status_code=500, detail="Erro ao gerar PDF")

    return FileResponse(
        path=str(pdf_path),
        filename=pdf_name,
        media_type="application/pdf",
    )
