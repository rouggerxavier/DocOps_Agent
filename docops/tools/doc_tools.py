"""DocOps Agent tools — callable by the graph nodes or CLI commands."""

from pathlib import Path
from typing import Any, List, Optional

from langchain_core.documents import Document

from docops.config import config
from docops.logging import get_logger

def _markdown_to_pdf(content: str, output_path: Path) -> None:
    """Convert Markdown text to a PDF file using fpdf2."""
    from fpdf import FPDF

    class _PDF(FPDF):
        def header(self):
            pass

    pdf = _PDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    import unicodedata

    def _pick_unicode_fonts() -> tuple[Path | None, Path | None]:
        """Pick a Unicode-capable regular/bold font available on the host."""
        candidates = [
            (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
            (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf")),
            (
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            ),
            (
                Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
                Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            ),
            (
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            ),
        ]

        for regular, bold in candidates:
            if regular.exists():
                return regular, bold if bold.exists() else None
        return None, None

    font_family = "Helvetica"
    body_style = ""
    heading_style = "B"

    regular_font, bold_font = _pick_unicode_fonts()
    if regular_font:
        font_family = "DocOpsUnicode"
        pdf.add_font(font_family, "", str(regular_font))
        if bold_font:
            pdf.add_font(font_family, "B", str(bold_font))
        else:
            heading_style = ""

    def _fix_mojibake(text: str) -> str:
        """Fix common UTF-8 text incorrectly decoded as cp1252/latin-1."""
        markers = ("Ã", "Â", "â", "ð", "�")
        if not any(m in text for m in markers):
            return text

        candidates = [text]
        for source_encoding in ("cp1252", "latin-1"):
            try:
                candidates.append(text.encode(source_encoding).decode("utf-8"))
            except UnicodeError:
                pass

        def _marker_score(value: str) -> int:
            return sum(value.count(m) for m in markers)

        best = min(candidates, key=_marker_score)
        return best if _marker_score(best) < _marker_score(text) else text

    def _safe(text: str) -> str:
        text = _fix_mojibake(text)
        # Mantém unicode para preservar acentos/símbolos e reduz glyphs exóticos.
        text = unicodedata.normalize("NFKC", text)
        # Remove apenas controles invisíveis que podem quebrar layout.
        text = "".join(
            ch for ch in text if ch == "\t" or unicodedata.category(ch)[0] != "C"
        )
        text = text.expandtabs(2)
        # Fallback para fontes core (não unicode) se não acharmos TTF.
        if font_family == "Helvetica":
            text = text.encode("latin-1", errors="replace").decode("latin-1")
        # Quebra tokens sem espaço que sejam muito longos
        words = text.split(" ")
        result = []
        for word in words:
            if len(word) > 60:
                result.extend([word[i:i+60] for i in range(0, len(word), 60)])
            else:
                result.append(word)
        return " ".join(result)

    def _write_line(text: str, height: int) -> None:
        """Render one wrapped line and keep the cursor anchored on left margin."""
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(font_family, body_style, 11)

    for line in content.splitlines():
        if line.startswith("# "):
            pdf.set_font(font_family, heading_style, 16)
            _write_line(_safe(line[2:].strip()), 8)
            pdf.set_font(font_family, body_style, 11)
        elif line.startswith("## "):
            pdf.set_font(font_family, heading_style, 13)
            _write_line(_safe(line[3:].strip()), 7)
            pdf.set_font(font_family, body_style, 11)
        elif line.startswith("### "):
            pdf.set_font(font_family, heading_style, 11)
            _write_line(_safe(line[4:].strip()), 6)
            pdf.set_font(font_family, body_style, 11)
        elif line.startswith("- ") or line.startswith("* "):
            _write_line(_safe(f"  - {line[2:].strip()}"), 6)
        elif line.strip() == "":
            pdf.ln(3)
        else:
            _write_line(_safe(line), 6)

    pdf.output(str(output_path))

logger = get_logger("docops.tools.doc_tools")


# ── tool_search_docs ─────────────────────────────────────────────────────────

def tool_search_docs(query: str, top_k: Optional[int] = None) -> List[Document]:
    """Search the indexed documents and return matching chunks as Documents.

    This is a LangChain/LangGraph-compatible tool used by graph nodes for
    retrieval. Returns LangChain Document objects so the graph state contract
    (retrieved_chunks: List[Document]) is preserved for citations/sources.

    Args:
        query: Search query string.
        top_k: Number of results to return. Defaults to config.top_k.

    Returns:
        List of Document objects with metadata (source, file_name, page, chunk_id).
    """
    from docops.rag.retriever import retrieve

    k = top_k or config.top_k
    chunks = retrieve(query, top_k=k)

    scores = [c.metadata.get("retrieval_score", "n/a") for c in chunks]
    logger.debug(
        f"tool_search_docs: {len(chunks)} chunks (mode={config.retrieval_mode}, "
        f"scores={scores}) for '{query[:50]}'"
    )
    return chunks


# ── tool_read_chunk ──────────────────────────────────────────────────────────

def tool_read_chunk(chunk_id: str) -> Optional[dict[str, Any]]:
    """Read a full chunk by its chunk_id from the Chroma vector store.

    Args:
        chunk_id: UUID string assigned during ingestion.

    Returns:
        Dict with text, metadata, or None if not found.
    """
    from docops.ingestion.indexer import get_vectorstore

    vectorstore = get_vectorstore()
    collection = vectorstore._collection

    result = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    if not docs:
        logger.warning(f"tool_read_chunk: chunk_id '{chunk_id}' not found.")
        return None

    return {
        "chunk_id": chunk_id,
        "text": docs[0],
        "metadata": metas[0] if metas else {},
    }


# ── tool_write_artifact ──────────────────────────────────────────────────────

def tool_write_artifact(filename: str, content: str) -> Path:
    """Write content to a file in the artifacts directory.

    Args:
        filename: File name (e.g., 'summary.md'). Will be placed in artifacts/.
        content: Text content to write.

    Returns:
        Path to the written file.
    """
    artifacts_dir = config.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename (no path traversal)
    safe_name = Path(filename).name
    output_path = artifacts_dir / safe_name

    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Artifact written: {output_path}")
    return output_path


# ── tool_list_docs ────────────────────────────────────────────────────────────

def tool_list_docs() -> List[dict[str, Any]]:
    """List all documents currently indexed in the Chroma vector store.

    Returns:
        List of dicts with file_name, source, chunk_count.
    """
    from docops.ingestion.indexer import list_indexed_docs

    docs = list_indexed_docs()
    logger.debug(f"tool_list_docs: {len(docs)} unique documents found.")
    return docs
