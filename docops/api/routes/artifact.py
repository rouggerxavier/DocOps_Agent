"""Artifact endpoints: POST /api/artifact, GET /api/artifacts, GET /api/artifacts/{filename}."""

from __future__ import annotations

import asyncio
import mimetypes
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from docops.api.schemas import ArtifactItem, ArtifactRequest, ArtifactResponse
from docops.auth.dependencies import get_current_user
from docops.config import config  # kept for backward-compatible test patching
from docops.db.crud import create_artifact_record, list_artifacts_for_user
from docops.db.database import get_db
from docops.db.models import User
from docops.logging import get_logger
from docops.services.ownership import require_user_artifact, require_user_document
from docops.storage.paths import get_user_artifacts_dir

logger = get_logger("docops.api.artifact")
router = APIRouter()


def _safe_stem(text: str, limit: int = 48) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    stem = stem.strip("._-") or "artifact"
    return stem[:limit]


def _run_artifact(
    type_: str,
    topic: str,
    output: str | None,
    user_id: int,
    doc_names: list[str] | None = None,
    doc_ids: list[str] | None = None,
) -> dict:
    from docops.graph.graph import run
    from docops.tools.doc_tools import tool_write_artifact

    selected_docs = [name for name in (doc_names or []) if str(name).strip()]
    query = f"Gere um {type_} sobre: {topic}"
    if selected_docs:
        query += f". Use apenas os documentos: {', '.join(selected_docs)}."

    extra: dict[str, object] = {"topic": topic}
    if selected_docs:
        extra["doc_names"] = selected_docs
    if doc_ids:
        extra["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]

    state = dict(
        run(
            query=query,
            extra=extra,
            user_id=user_id,
        )
    )
    answer = state.get("answer", "")
    fname = output or f"{type_}_{_safe_stem(topic)}.md"
    path = tool_write_artifact(fname, answer, user_id=user_id)
    return {"answer": answer, "filename": path.name, "path": str(path)}


@router.post("/artifact", response_model=ArtifactResponse)
async def create_artifact(
    body: ArtifactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ArtifactResponse:
    """Generate and save a structured artifact scoped to the current user."""
    logger.info(f"Artifact: type={body.type}, topic='{body.topic[:50]}' for user {current_user.id}")
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
            doc_names,
            doc_ids,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(f"Artifact error: {exc}")
        raise HTTPException(status_code=500, detail="Agent error")

    create_artifact_record(
        db,
        user_id=current_user.id,
        artifact_type=body.type,
        title=body.topic[:512],
        filename=result["filename"],
        path=result["path"],
        source_doc_id=doc_ids[0] if len(doc_ids) >= 1 else None,
        source_doc_id_2=doc_ids[1] if len(doc_ids) >= 2 else None,
    )

    return ArtifactResponse(**result)


@router.get("/artifacts", response_model=List[ArtifactItem])
async def list_artifacts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ArtifactItem]:
    """List all saved artifacts for the current user (source: SQL)."""
    records = list_artifacts_for_user(db, current_user.id)
    items = []
    for r in records:
        p = Path(r.path)
        size = p.stat().st_size if p.exists() else 0
        items.append(
            ArtifactItem(
                filename=r.filename,
                size=size,
                created_at=r.created_at.isoformat(),
                artifact_type=r.artifact_type,
                title=r.title,
            )
        )
    return items


@router.get("/artifacts/{filename}")
async def download_artifact(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a specific artifact file — ownership validated."""
    require_user_artifact(db, current_user.id, filename)

    safe_name = Path(filename).name
    artifact_path = get_user_artifacts_dir(current_user.id) / safe_name

    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {filename}")

    media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    return FileResponse(
        path=str(artifact_path),
        filename=safe_name,
        media_type=media_type,
    )


@router.get("/artifacts/{filename}/pdf")
async def download_artifact_pdf(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Convert a Markdown artifact to PDF and return it for download — ownership validated."""
    import tempfile
    from docops.tools.doc_tools import _markdown_to_pdf

    require_user_artifact(db, current_user.id, filename)

    safe_name = Path(filename).name
    artifact_path = get_user_artifacts_dir(current_user.id) / safe_name

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
