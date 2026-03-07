"""Ingest endpoints: ingest from path or upload, scoped per user."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from docops.api.schemas import IngestPathRequest, IngestResponse
from docops.auth.dependencies import get_current_user
from docops.config import config
from docops.db.crud import create_document_record
from docops.db.database import get_db
from docops.db.models import User
from docops.ingestion.metadata import build_doc_id, infer_file_type
from docops.logging import get_logger
from docops.storage.paths import get_user_upload_dir

logger = get_logger("docops.api.ingest")
router = APIRouter()


def _file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(8192), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_ingest(
    user_id: int,
    paths: List[Path],
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[IngestResponse, list[dict]]:
    """Run ingestion/indexing for a user and return SQL registration payload."""
    from docops.ingestion.indexer import index_chunks_for_user
    from docops.ingestion.loaders import load_directory, load_file
    from docops.ingestion.splitter import split_documents
    from docops.rag.hybrid import build_bm25_index_for_user

    effective_chunk_size = chunk_size or config.chunk_size
    effective_chunk_overlap = chunk_overlap or config.chunk_overlap

    all_docs = []
    for path in paths:
        if path.is_dir():
            loaded_docs = load_directory(path)
        elif path.is_file():
            loaded_docs = load_file(path)
        else:
            raise HTTPException(status_code=400, detail=f"Path not found: {path}")

        for doc in loaded_docs:
            source_path = str(doc.metadata.get("source_path") or doc.metadata.get("source") or path)
            source_path = source_path.replace("\\", "/")
            doc.metadata["user_id"] = user_id
            doc.metadata["source_path"] = source_path
            doc.metadata["source"] = source_path
            doc.metadata["storage_path"] = str(doc.metadata.get("storage_path") or source_path)
            doc.metadata["doc_id"] = build_doc_id(source_path, user_id=user_id)
            doc.metadata["file_type"] = infer_file_type(doc.metadata)

        all_docs.extend(loaded_docs)

    if not all_docs:
        return IngestResponse(files_loaded=0, chunks_indexed=0, file_names=[]), []

    chunks = split_documents(
        all_docs,
        chunk_size=effective_chunk_size,
        chunk_overlap=effective_chunk_overlap,
        stable_ids=True,
    )

    for chunk in chunks:
        chunk.metadata["user_id"] = user_id

    indexed = index_chunks_for_user(user_id=user_id, chunks=chunks)
    build_bm25_index_for_user(user_id=user_id, chunks=chunks)

    docs_map: dict[str, dict] = {}
    for chunk in chunks:
        metadata = chunk.metadata
        doc_id = str(metadata.get("doc_id") or "")
        if not doc_id:
            continue

        source_path = str(metadata.get("source_path") or metadata.get("source") or "")
        storage_path = str(metadata.get("storage_path") or source_path)
        file_name = str(metadata.get("file_name") or Path(source_path).name)

        if doc_id not in docs_map:
            docs_map[doc_id] = {
                "user_id": user_id,
                "doc_id": doc_id,
                "file_name": file_name,
                "original_filename": file_name,
                "source_path": source_path,
                "storage_path": storage_path,
                "file_type": str(metadata.get("file_type") or infer_file_type(metadata)),
                "chunk_count": 0,
                "sha256_hash": _file_sha256(Path(storage_path)),
            }

        docs_map[doc_id]["chunk_count"] += 1

    response = IngestResponse(
        files_loaded=len(all_docs),
        chunks_indexed=indexed,
        file_names=sorted({entry["file_name"] for entry in docs_map.values()}),
    )
    return response, list(docs_map.values())


@router.post("/ingest", response_model=IngestResponse)
async def ingest_by_path(
    body: IngestPathRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Ingest a local server path into current_user scope."""
    path = Path(body.path).resolve()

    allowed_dirs = [allowed.resolve() for allowed in config.ingest_allowed_dirs]
    if not any(str(path).startswith(str(allowed)) for allowed in allowed_dirs):
        allowed_label = ", ".join(str(allowed) for allowed in allowed_dirs)
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Path must be under: {allowed_label}",
        )

    if not path.exists():
        raise HTTPException(status_code=400, detail=f"Path not found: {body.path}")

    logger.info("Ingest path for user %s: %s", current_user.id, path)
    result, records = await asyncio.to_thread(
        _run_ingest,
        current_user.id,
        [path],
        body.chunk_size,
        body.chunk_overlap,
    )

    for record in records:
        create_document_record(db, **record)

    return result


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    files: List[UploadFile] = File(...),
    chunk_size: int = Form(default=0),
    chunk_overlap: int = Form(default=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Upload and ingest one or more files into current_user scope."""
    from docops.ingestion.loaders import SUPPORTED_EXTENSIONS

    upload_dir = get_user_upload_dir(current_user.id)
    saved_paths: list[Path] = []

    for upload in files:
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
            )

        safe_name = Path(upload.filename or f"upload{ext}").name
        destination = upload_dir / safe_name
        destination.write_bytes(await upload.read())
        saved_paths.append(destination)

    logger.info("Ingest upload for user %s: %s files", current_user.id, len(saved_paths))
    result, records = await asyncio.to_thread(
        _run_ingest,
        current_user.id,
        saved_paths,
        chunk_size,
        chunk_overlap,
    )

    for record in records:
        create_document_record(db, **record)

    return result
