"""Document loaders for PDF, Markdown, and plain text files."""

from pathlib import Path
from typing import List

from langchain_core.documents import Document

from docops.ingestion.metadata import build_doc_id
from docops.logging import get_logger

logger = get_logger("docops.ingestion.loaders")


def load_pdf(file_path: Path) -> List[Document]:
    """Load a PDF file, one Document per page, with page metadata."""
    try:
        import pypdf
    except ImportError:
        raise ImportError("pypdf is required for PDF loading: pip install pypdf")

    logger.info(f"Loading PDF: {file_path}")
    source_path = str(file_path)
    doc_id = build_doc_id(source_path)
    docs = []

    with open(file_path, "rb") as f:
        reader = pypdf.PdfReader(f)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            page_no = i + 1
            docs.append(Document(
                page_content=text,
                metadata={
                    "file_name": file_path.name,
                    "source": source_path,
                    "source_path": source_path,
                    "doc_id": doc_id,
                    "file_type": "pdf",
                    "page": page_no,
                    "page_start": page_no,
                    "page_end": page_no,
                    "section_title": "",
                    "section_path": "",
                },
            ))

    logger.info(f"Loaded {len(docs)} pages from {file_path.name}")
    return docs


def load_text(file_path: Path) -> List[Document]:
    """Load a plain text (.txt) file as a single Document."""
    logger.info(f"Loading TXT: {file_path}")
    content = file_path.read_text(encoding="utf-8", errors="replace")
    source_path = str(file_path)
    doc = Document(
        page_content=content,
        metadata={
            "file_name": file_path.name,
            "source": source_path,
            "source_path": source_path,
            "doc_id": build_doc_id(source_path),
            "file_type": "txt",
            "page": "N/A",
            "page_start": "N/A",
            "page_end": "N/A",
            "section_title": "",
            "section_path": "",
        },
    )
    return [doc]


def load_markdown(file_path: Path) -> List[Document]:
    """Load a Markdown file as a single Document."""
    logger.info(f"Loading MD: {file_path}")
    content = file_path.read_text(encoding="utf-8", errors="replace")
    source_path = str(file_path)
    doc = Document(
        page_content=content,
        metadata={
            "file_name": file_path.name,
            "source": source_path,
            "source_path": source_path,
            "doc_id": build_doc_id(source_path),
            "file_type": "md",
            "page": "N/A",
            "page_start": "N/A",
            "page_end": "N/A",
            "section_title": "",
            "section_path": "",
        },
    )
    return [doc]


_LOADERS = {
    ".pdf": load_pdf,
    ".txt": load_text,
    ".md": load_markdown,
    ".markdown": load_markdown,
}

SUPPORTED_EXTENSIONS = set(_LOADERS.keys())


def load_file(file_path: Path) -> List[Document]:
    """Dispatch to the correct loader based on file extension."""
    ext = file_path.suffix.lower()
    loader_fn = _LOADERS.get(ext)
    if loader_fn is None:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return loader_fn(file_path)


def load_directory(dir_path: Path) -> List[Document]:
    """Load all supported documents from a directory (non-recursive)."""
    dir_path = Path(dir_path)
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    all_docs: List[Document] = []
    found_files = [
        f for f in sorted(dir_path.iterdir())
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not found_files:
        logger.warning(
            f"No supported files found in '{dir_path}'. "
            f"Add PDF, MD, or TXT files and run ingest again."
        )
        return []

    for file_path in found_files:
        try:
            docs = load_file(file_path)
            all_docs.extend(docs)
        except Exception as exc:
            logger.error(f"Failed to load '{file_path.name}': {exc}")

    logger.info(f"Loaded {len(all_docs)} document chunks from {len(found_files)} files")
    return all_docs
