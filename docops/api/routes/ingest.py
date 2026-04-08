"""Ingest endpoints: ingest from path, upload, clip text, or photo OCR."""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
import unicodedata
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
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


# ── Schemas para clip ─────────────────────────────────────────────────────────

class ClipRequest(BaseModel):
    text: str = Field(min_length=10, max_length=50000)
    title: str = Field(default="clip", min_length=1, max_length=255)


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

        safe_name = unicodedata.normalize("NFC", Path(upload.filename or f"upload{ext}").name)
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


class UrlIngestRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    title: str = Field(default="", max_length=255)


def _is_youtube_url(url: str) -> bool:
    return "youtube.com/watch" in url or "youtu.be/" in url


def _get_youtube_transcript(url: str) -> str:
    """Extrai transcrição de um vídeo do YouTube.

    Tenta primeiro o youtube-transcript-api (rápido). Se o IP estiver bloqueado
    pelo YouTube (comum em servidores cloud), cai para yt-dlp que tem melhor
    evasão de bloqueios.
    """
    import re as _re

    match = _re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    if not match:
        raise ValueError("Não foi possível extrair o ID do vídeo do YouTube.")
    video_id = match.group(1)

    # ── Tentativa 1: youtube-transcript-api ──────────────────────────────────
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        try:
            transcript_list = api.list(video_id)
            try:
                transcript = transcript_list.find_transcript(["pt", "pt-BR", "en"])
            except Exception:
                transcript = next(iter(transcript_list))
            fetched = transcript.fetch()
        except Exception:
            fetched = api.fetch(video_id)

        text = " ".join(entry.text for entry in fetched)
        if text.strip():
            return text
    except Exception as primary_err:
        logger.warning("youtube-transcript-api falhou (%s), tentando yt-dlp…", primary_err)

    # ── Tentativa 2: yt-dlp (melhor evasão de bloqueio de IP) ────────────────
    try:
        import tempfile, os, json as _json
        import yt_dlp  # type: ignore

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["pt", "pt-BR", "en", "en-US"],
                "subtitlesformat": "json3",
                "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                ydl.download([url])

            # Procura arquivo de legenda gerado (.json3)
            subtitle_text = ""
            for fname in os.listdir(tmpdir):
                if fname.endswith(".json3"):
                    fpath = os.path.join(tmpdir, fname)
                    with open(fpath, encoding="utf-8") as f:
                        data = _json.load(f)
                    events = data.get("events", [])
                    words = []
                    for event in events:
                        for seg in event.get("segs", []):
                            w = seg.get("utf8", "").strip()
                            if w and w != "\n":
                                words.append(w)
                    subtitle_text = " ".join(words)
                    break

            if subtitle_text.strip():
                return subtitle_text

            # Fallback: usa a descrição + título do vídeo se não há legendas
            title = (info or {}).get("title", "")
            description = (info or {}).get("description", "")
            if title or description:
                return f"{title}\n\n{description}"

    except Exception as ytdlp_err:
        logger.error("yt-dlp também falhou: %s", ytdlp_err)

    raise RuntimeError(
        "Não foi possível extrair a transcrição deste vídeo. "
        "O YouTube está bloqueando o IP do servidor. "
        "Tente baixar a transcrição manualmente e fazer upload como arquivo de texto."
    )


async def _fetch_webpage_text(url: str) -> str:
    """Busca e extrai o texto principal de uma página web."""
    import httpx
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, verify=False) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html = response.text

    soup = BeautifulSoup(html, "html.parser")
    # Remove scripts, styles, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Tenta extrair conteúdo principal
    main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.body
    text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)

    # Limpa linhas muito curtas / vazias
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 30]
    return "\n".join(lines)


@router.post("/ingest/url", response_model=IngestResponse)
async def ingest_url(
    body: UrlIngestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Ingest content from a URL or YouTube video."""
    import re as _re

    url = body.url.strip()

    # Título: usa o fornecido ou extrai do domínio/ID
    if body.title.strip():
        title = body.title.strip()
    elif _is_youtube_url(url):
        match = _re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
        title = f"youtube_{match.group(1)}" if match else "youtube_video"
    else:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
        title = domain or "webpage"

    logger.info("Ingest URL para user %s: %s", current_user.id, url)

    try:
        if _is_youtube_url(url):
            text = await asyncio.to_thread(_get_youtube_transcript, url)
        else:
            text = await _fetch_webpage_text(url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Falha ao extrair conteúdo da URL: {exc}")

    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=422, detail="Conteúdo insuficiente extraído da URL.")

    upload_dir = get_user_upload_dir(current_user.id)
    safe_title = "".join(
        c if (unicodedata.category(c)[0] in ("L", "N") or c in " _-") else "_"
        for c in unicodedata.normalize("NFC", title)
    )[:100]
    filename = f"{safe_title}.txt"
    destination = upload_dir / filename
    destination.write_text(text, encoding="utf-8")

    logger.info("Ingest URL salvo: %s (%d chars)", filename, len(text))
    result, records = await asyncio.to_thread(
        _run_ingest, current_user.id, [destination], 0, 0,
    )
    for record in records:
        create_document_record(db, **record)
    return result


@router.post("/ingest/clip", response_model=IngestResponse)
async def ingest_clip(
    body: ClipRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Ingest raw text (clipboard, URL content, etc.) as a .txt file."""
    upload_dir = get_user_upload_dir(current_user.id)
    safe_title = "".join(
        c if (unicodedata.category(c)[0] in ("L", "N") or c in " _-") else "_"
        for c in unicodedata.normalize("NFC", body.title)
    )[:100]
    filename = f"{safe_title}.txt"
    destination = upload_dir / filename
    destination.write_text(body.text, encoding="utf-8")

    logger.info("Ingest clip for user %s: %s (%d chars)", current_user.id, filename, len(body.text))
    result, records = await asyncio.to_thread(
        _run_ingest, current_user.id, [destination], 0, 0,
    )
    for record in records:
        create_document_record(db, **record)
    return result


@router.post("/ingest/photo", response_model=IngestResponse)
async def ingest_photo(
    file: UploadFile = File(...),
    title: str = Form(default="foto"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    """Upload a photo, extract text via OCR (Gemini Vision), and ingest."""
    allowed_types = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de imagem nao suportado: {ext}. Use: {sorted(allowed_types)}",
        )

    image_bytes = await file.read()
    extracted = await asyncio.to_thread(_ocr_with_gemini, image_bytes, ext)

    if not extracted or len(extracted.strip()) < 10:
        raise HTTPException(status_code=422, detail="Nao foi possivel extrair texto da imagem.")

    upload_dir = get_user_upload_dir(current_user.id)
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:100]
    filename = f"{safe_title}_ocr.txt"
    destination = upload_dir / filename
    destination.write_text(extracted, encoding="utf-8")

    logger.info("Ingest photo OCR for user %s: %s (%d chars)", current_user.id, filename, len(extracted))
    result, records = await asyncio.to_thread(
        _run_ingest, current_user.id, [destination], 0, 0,
    )
    for record in records:
        create_document_record(db, **record)
    return result


def _ocr_with_gemini(image_bytes: bytes, ext: str) -> str:
    """Use Gemini Vision to extract text from an image."""
    from google import genai
    from google.genai import types

    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".heic": "image/heic",
    }
    mime = mime_map.get(ext, "image/jpeg")

    client = genai.Client(api_key=config.gemini_api_key)
    response = client.models.generate_content(
        model=config.gemini_model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            "Extraia TODO o texto visivel nesta imagem. "
            "Transcreva fielmente mantendo a estrutura (paragrafos, listas, titulos). "
            "Retorne APENAS o texto extraido, sem comentarios.",
        ],
    )
    return response.text.strip()
