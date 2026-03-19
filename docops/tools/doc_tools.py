"""DocOps Agent tools — callable by the graph nodes or CLI commands."""

from pathlib import Path
from typing import Any, List, Optional

from langchain_core.documents import Document

from docops.config import config
from docops.logging import get_logger
from docops.storage.paths import get_user_artifacts_dir

def _markdown_to_pdf(content: str, output_path: Path) -> None:
    """Convert Markdown text to a styled PDF using fpdf2.

    Handles bold (**text**), headings (#/##/###), bullets, inline
    citations [Fonte N], and renders a clean "Referências" section at
    the end instead of raw markdown source lines.
    """
    import re
    import unicodedata

    from fpdf import FPDF

    # ── regex for inline citations and the Fontes: section ──────────
    _RE_FONTE = re.compile(r"\s*\[Fonte\s*\d+\]", re.IGNORECASE)
    _RE_FONTES_HEADER = re.compile(
        r"^\*{0,2}Fontes:\*{0,2}\s*$", re.IGNORECASE
    )
    _RE_FONTE_LINE = re.compile(
        r"^-\s*\[Fonte\s*\d+\]\s*\*{0,2}(.+?)\*{0,2}\s*(?:—\s*_.*_)?\s*$",
        re.IGNORECASE,
    )
    _RE_BOLD = re.compile(r"\*\*(.+?)\*\*")

    # ── separate body from Fontes: section ──────────────────────────
    body_lines: list[str] = []
    references: list[str] = []
    in_fontes = False

    for raw_line in content.splitlines():
        if _RE_FONTES_HEADER.match(raw_line.strip()):
            in_fontes = True
            continue
        if in_fontes:
            m = _RE_FONTE_LINE.match(raw_line.strip())
            if m:
                references.append(m.group(1).strip())
            elif raw_line.strip().startswith("- "):
                # Fallback: any bullet in the Fontes block
                cleaned = raw_line.strip().lstrip("- ").strip()
                cleaned = _RE_BOLD.sub(r"\1", cleaned)
                if cleaned:
                    references.append(cleaned)
            continue
        body_lines.append(raw_line)

    # ── PDF setup ───────────────────────────────────────────────────
    class _PDF(FPDF):
        def header(self):
            pass

    pdf = _PDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def _pick_unicode_fonts() -> tuple[Path | None, Path | None]:
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

    has_bold_font = heading_style == "B"

    def _fix_mojibake(text: str) -> str:
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
        text = unicodedata.normalize("NFKC", text)
        text = "".join(
            ch for ch in text if ch == "\t" or unicodedata.category(ch)[0] != "C"
        )
        text = text.expandtabs(2)
        if font_family == "Helvetica":
            text = text.encode("latin-1", errors="replace").decode("latin-1")
        words = text.split(" ")
        result = []
        for word in words:
            if len(word) > 60:
                result.extend([word[i : i + 60] for i in range(0, len(word), 60)])
            else:
                result.append(word)
        return " ".join(result)

    def _write_line(text: str, height: int) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")

    def _write_rich_line(text: str, height: int) -> None:
        """Write a line handling **bold** segments as real bold in the PDF."""
        segments = _RE_BOLD.split(text)
        if len(segments) <= 1 or not has_bold_font:
            # No bold markers or no bold font available — write plain
            _write_line(_safe(text), height)
            return
        # Render segment by segment using multi_cell for proper wrapping.
        # fpdf2 doesn't support inline style changes inside multi_cell,
        # so we use write() which flows inline.
        pdf.set_x(pdf.l_margin)
        for idx, seg in enumerate(segments):
            if not seg:
                continue
            is_bold = idx % 2 == 1  # odd segments are inside **...**
            pdf.set_font(font_family, "B" if is_bold else body_style, pdf.font_size_pt)
            pdf.write(height, _safe(seg))
        pdf.set_font(font_family, body_style, 11)
        pdf.ln(height)

    def _strip_citations(text: str) -> str:
        """Remove [Fonte N] markers from text."""
        return _RE_FONTE.sub("", text)

    # ── render body ─────────────────────────────────────────────────
    pdf.set_font(font_family, body_style, 11)

    for line in body_lines:
        line = _strip_citations(line)
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
            clean = _RE_BOLD.sub(r"\1", line[2:].strip())
            _write_line(_safe(f"  \u2022 {clean}"), 6)
        elif line.strip() == "":
            pdf.ln(3)
        else:
            _write_rich_line(line, 6)

    # ── render Referências section ──────────────────────────────────
    if references:
        pdf.ln(8)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(5)

        pdf.set_font(font_family, heading_style, 13)
        _write_line("Referências", 7)
        pdf.set_font(font_family, body_style, 9)
        pdf.ln(2)

        for idx, ref in enumerate(references, start=1):
            ref_clean = _RE_BOLD.sub(r"\1", ref)
            ref_clean = _RE_FONTE.sub("", ref_clean).strip()
            _write_line(_safe(f"[{idx}]  {ref_clean}"), 5)

    pdf.output(str(output_path))

logger = get_logger("docops.tools.doc_tools")


# ── tool_search_docs ─────────────────────────────────────────────────────────

def tool_search_docs(
    query: str,
    user_id: int,
    top_k: Optional[int] = None,
    doc_names: Optional[List[str]] = None,
    doc_ids: Optional[List[str]] = None,
) -> List[Document]:
    """Search the user's indexed documents and return matching chunks."""
    from docops.rag.retriever import retrieve, retrieve_for_docs

    k = top_k or config.top_k
    clean_doc_names = [str(name).strip() for name in (doc_names or []) if str(name).strip()]
    clean_doc_ids = [str(doc_id).strip() for doc_id in (doc_ids or []) if str(doc_id).strip()]
    if clean_doc_names or clean_doc_ids:
        chunks = retrieve_for_docs(
            clean_doc_names,
            query=query,
            top_k=k,
            user_id=user_id,
            doc_ids=clean_doc_ids,
        )
    else:
        chunks = retrieve(query, user_id=user_id, top_k=k)

    scores = [c.metadata.get("retrieval_score", "n/a") for c in chunks]
    logger.debug(
        f"tool_search_docs (user={user_id}): {len(chunks)} chunks (mode={config.retrieval_mode}, "
        f"scores={scores}) for '{query[:50]}'"
    )
    return chunks


# ── tool_read_chunk ──────────────────────────────────────────────────────────

def tool_read_chunk(chunk_id: str, user_id: int) -> Optional[dict[str, Any]]:
    """Read a full chunk by its chunk_id from the user's Chroma collection."""
    from docops.ingestion.indexer import get_vectorstore_for_user

    vectorstore = get_vectorstore_for_user(user_id)
    collection = vectorstore._collection

    result = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    if not docs:
        logger.warning(f"tool_read_chunk: chunk_id '{chunk_id}' not found for user {user_id}.")
        return None

    return {
        "chunk_id": chunk_id,
        "text": docs[0],
        "metadata": metas[0] if metas else {},
    }


# ── tool_write_artifact ──────────────────────────────────────────────────────

def tool_write_artifact(filename: str, content: str, user_id: int) -> Path:
    """Write content to a file in the user's artifacts directory."""
    artifacts_dir = get_user_artifacts_dir(user_id)
    safe_name = Path(filename).name
    output_path = artifacts_dir / safe_name
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Artifact written for user {user_id}: {output_path}")
    return output_path


# ── tool_list_docs ────────────────────────────────────────────────────────────

def tool_list_docs(user_id: int) -> List[dict[str, Any]]:
    """List all documents currently indexed for the user."""
    from docops.ingestion.indexer import list_indexed_docs_for_user

    docs = list_indexed_docs_for_user(user_id)
    logger.debug(f"tool_list_docs (user={user_id}): {len(docs)} unique documents found.")
    return docs
