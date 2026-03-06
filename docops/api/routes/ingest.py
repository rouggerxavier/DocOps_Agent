"""Ingest endpoints: POST /api/ingest (JSON path) and POST /api/ingest/upload (multipart)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse

from docops.api.schemas import IngestPathRequest, IngestResponse
from docops.config import config
from docops.logging import get_logger

logger = get_logger("docops.api.ingest")
router = APIRouter()


def _run_ingest(paths: List[Path], chunk_size: int, chunk_overlap: int) -> IngestResponse:
    """Synchronous ingestion pipeline — call in threadpool."""
    from docops.ingestion.loaders import load_file, load_directory
    from docops.ingestion.splitter import split_documents
    from docops.ingestion.indexer import index_chunks

    cs = chunk_size or config.chunk_size
    co = chunk_overlap or config.chunk_overlap

    all_docs = []
    file_names: List[str] = []

    for p in paths:
        if p.is_dir():
            docs = load_directory(p)
        elif p.is_file():
            docs = load_file(p)
        else:
            raise HTTPException(status_code=400, detail=f"Path not found: {p}")
        all_docs.extend(docs)
        file_names.extend({d.metadata.get("file_name", p.name) for d in docs})

    if not all_docs:
        return IngestResponse(files_loaded=0, chunks_indexed=0, file_names=[])

    chunks = split_documents(all_docs, chunk_size=cs, chunk_overlap=co)
    indexed = index_chunks(chunks)

    # Build BM25 index for hybrid search
    from docops.rag.hybrid import build_bm25_index
    build_bm25_index(chunks)

    unique_files = sorted(set(file_names))
    return IngestResponse(
        files_loaded=len(all_docs),
        chunks_indexed=indexed,
        file_names=unique_files,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_by_path(body: IngestPathRequest) -> IngestResponse:
    """Ingest documents from a local server path (directory or file)."""
    p = Path(body.path).resolve()

    # Allowlist: só permite paths dentro dos diretórios autorizados
    allowed = config.ingest_allowed_dirs
    if not any(str(p).startswith(str(d)) for d in allowed):
        allowed_str = ", ".join(str(d) for d in allowed)
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado. O path deve estar dentro de: {allowed_str}",
        )

    if not p.exists():
        raise HTTPException(status_code=400, detail=f"Path não encontrado: {body.path}")

    logger.info(f"Ingesting path: {p}")
    result = await asyncio.to_thread(
        _run_ingest, [p], body.chunk_size, body.chunk_overlap
    )
    return result


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    files: List[UploadFile] = File(...),
    chunk_size: int = Form(default=0),
    chunk_overlap: int = Form(default=0),
) -> IngestResponse:
    """Upload one or more files and ingest them into the vector store."""
    from docops.ingestion.loaders import SUPPORTED_EXTENSIONS

    tmp_paths: List[Path] = []

    for upload in files:
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
            )

        # Write to temp file preserving extension so loaders detect type
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            content = await upload.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # Rename so file_name metadata is meaningful
        named_path = tmp_path.parent / (upload.filename or tmp_path.name)
        tmp_path.rename(named_path)
        tmp_paths.append(named_path)

    try:
        logger.info(f"Ingesting {len(tmp_paths)} uploaded file(s)")
        result = await asyncio.to_thread(
            _run_ingest, tmp_paths, chunk_size, chunk_overlap
        )
    finally:
        for p in tmp_paths:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

    return result
