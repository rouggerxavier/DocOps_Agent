"""Tests for structured (Markdown + TXT) splitters."""

import pytest
from langchain_core.documents import Document


# ── Helpers ───────────────────────────────────────────────────────────────────

def _md_doc(text: str, file_name: str = "test.md") -> Document:
    return Document(
        page_content=text,
        metadata={"file_name": file_name, "source": f"docs/{file_name}", "page": None},
    )


def _txt_doc(text: str, file_name: str = "test.txt") -> Document:
    return Document(
        page_content=text,
        metadata={"file_name": file_name, "source": f"docs/{file_name}", "page": None},
    )


# ── Markdown splitter ─────────────────────────────────────────────────────────

class TestMarkdownSplitter:
    def test_headings_detected(self):
        from docops.ingestion.md_splitter import split_markdown

        text = "# Título Principal\n\nConteúdo da seção 1.\n\n## Sub-seção\n\nConteúdo da sub-seção."
        doc = _md_doc(text)
        chunks = split_markdown(doc, chunk_size=900, chunk_overlap=0)

        assert len(chunks) >= 2

    def test_section_title_metadata(self):
        from docops.ingestion.md_splitter import split_markdown

        text = "# Arquitetura\n\nTexto da arquitetura.\n\n## Retrieval\n\nTexto do retrieval."
        doc = _md_doc(text)
        chunks = split_markdown(doc, chunk_size=900, chunk_overlap=0)

        titles = [c.metadata.get("section_title", "") for c in chunks]
        assert "Arquitetura" in titles
        assert "Retrieval" in titles

    def test_section_path_breadcrumb(self):
        from docops.ingestion.md_splitter import split_markdown

        text = (
            "# Arquitetura\n\nIntro.\n\n"
            "## Retrieval\n\nSub-section text.\n\n"
            "### Reranking\n\nDeep text."
        )
        doc = _md_doc(text)
        chunks = split_markdown(doc, chunk_size=900, chunk_overlap=0)

        # Find the deepest chunk
        paths = [c.metadata.get("section_path", "") for c in chunks]
        assert any("Arquitetura" in p and "Retrieval" in p for p in paths)
        assert any("Reranking" in p for p in paths)

    def test_chunk_ids_unique(self):
        from docops.ingestion.md_splitter import split_markdown

        text = "# A\n\nConteúdo A.\n\n# B\n\nConteúdo B.\n\n# C\n\nConteúdo C."
        doc = _md_doc(text)
        chunks = split_markdown(doc, chunk_size=900, chunk_overlap=0)

        ids = [c.metadata["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids)), "All chunk IDs must be unique"

    def test_file_type_is_md(self):
        from docops.ingestion.md_splitter import split_markdown

        doc = _md_doc("# Seção\n\nTexto da seção aqui.")
        chunks = split_markdown(doc, chunk_size=900, chunk_overlap=0)

        for c in chunks:
            assert c.metadata.get("file_type") == "md"

    def test_no_headings_fallback(self):
        from docops.ingestion.md_splitter import split_markdown

        text = "Texto simples sem nenhum heading. " * 50
        doc = _md_doc(text)
        # Should not raise; falls back to size-based
        chunks = split_markdown(doc, chunk_size=500, chunk_overlap=50)
        assert len(chunks) >= 1
        assert all(c.metadata.get("file_type") == "md" for c in chunks)

    def test_large_section_subdivided(self):
        from docops.ingestion.md_splitter import split_markdown

        # Create a large section
        big_content = "Linha de conteúdo muito importante. " * 100
        text = f"# Grande Seção\n\n{big_content}"
        doc = _md_doc(text)
        chunks = split_markdown(doc, chunk_size=500, chunk_overlap=50)

        # Should have multiple chunks, all with the same section_title
        assert len(chunks) > 1
        for c in chunks:
            assert c.metadata.get("section_title") == "Grande Seção"

    def test_preamble_before_heading(self):
        from docops.ingestion.md_splitter import split_markdown

        text = "Texto de introdução antes do primeiro heading.\n\n# Seção 1\n\nConteúdo."
        doc = _md_doc(text)
        chunks = split_markdown(doc, chunk_size=900, chunk_overlap=0)

        # Preamble chunk should have empty section_title
        preamble_chunks = [c for c in chunks if c.metadata.get("section_title") == ""]
        assert len(preamble_chunks) >= 1

    def test_metadata_preserved(self):
        from docops.ingestion.md_splitter import split_markdown

        doc = _md_doc("# Seção\n\nTexto.", file_name="manual.md")
        chunks = split_markdown(doc)

        for c in chunks:
            assert c.metadata["file_name"] == "manual.md"


# ── TXT splitter ──────────────────────────────────────────────────────────────

class TestTxtSplitter:
    def test_all_caps_heading_detected(self):
        from docops.ingestion.txt_splitter import split_txt, _is_heading_line

        assert _is_heading_line("INTRODUÇÃO")
        assert _is_heading_line("ARQUITETURA DO SISTEMA")

    def test_colon_heading_detected(self):
        from docops.ingestion.txt_splitter import _is_heading_line

        assert _is_heading_line("Configuração:")
        assert _is_heading_line("Dependências do projeto:")

    def test_numbered_heading_detected(self):
        from docops.ingestion.txt_splitter import _is_heading_line

        assert _is_heading_line("1. Introdução")
        assert _is_heading_line("2.1 Sub-seção")

    def test_short_line_not_heading(self):
        from docops.ingestion.txt_splitter import _is_heading_line

        assert not _is_heading_line("OK")  # too short
        assert not _is_heading_line("a")

    def test_split_detects_sections(self):
        from docops.ingestion.txt_splitter import split_txt

        text = (
            "INTRODUÇÃO\n\n"
            "Este é o texto de introdução do documento.\n\n"
            "ARQUITETURA\n\n"
            "Este é o texto da arquitetura."
        )
        doc = _txt_doc(text)
        chunks = split_txt(doc, chunk_size=900, chunk_overlap=0)

        titles = [c.metadata.get("section_title", "") for c in chunks]
        assert "INTRODUÇÃO" in titles
        assert "ARQUITETURA" in titles

    def test_section_path_equals_title_for_txt(self):
        from docops.ingestion.txt_splitter import split_txt

        text = "SEÇÃO ÚNICA\n\nConteúdo da seção."
        doc = _txt_doc(text)
        chunks = split_txt(doc)

        for c in chunks:
            if c.metadata.get("section_title"):
                assert c.metadata["section_title"] == c.metadata["section_path"]

    def test_chunk_ids_unique(self):
        from docops.ingestion.txt_splitter import split_txt

        text = "SEÇÃO A\n\nTexto A.\n\nSEÇÃO B\n\nTexto B.\n\nSEÇÃO C\n\nTexto C."
        doc = _txt_doc(text)
        chunks = split_txt(doc)

        ids = [c.metadata["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids))

    def test_file_type_is_txt(self):
        from docops.ingestion.txt_splitter import split_txt

        doc = _txt_doc("Texto simples sem seções.")
        chunks = split_txt(doc)
        for c in chunks:
            assert c.metadata.get("file_type") == "txt"

    def test_large_section_subdivided(self):
        from docops.ingestion.txt_splitter import split_txt

        big = "Frase de conteúdo importante. " * 100
        text = f"SEÇÃO GRANDE\n\n{big}"
        doc = _txt_doc(text)
        chunks = split_txt(doc, chunk_size=300, chunk_overlap=50)

        assert len(chunks) > 1


# ── Dispatcher (split_documents routing) ─────────────────────────────────────

class TestSplitDocumentsDispatcher:
    def test_md_file_routed_to_md_splitter(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="# Seção\n\nTexto.",
            metadata={"file_name": "guia.md", "source": "docs/guia.md", "page": None},
        )
        chunks = split_documents([doc], structured=True)
        assert all(c.metadata.get("file_type") == "md" for c in chunks)

    def test_txt_file_routed_to_txt_splitter(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="SEÇÃO\n\nConteúdo.",
            metadata={"file_name": "nota.txt", "source": "docs/nota.txt", "page": None},
        )
        chunks = split_documents([doc], structured=True)
        assert all(c.metadata.get("file_type") == "txt" for c in chunks)

    def test_pdf_uses_size_splitter(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="Texto de um PDF qualquer. " * 50,
            metadata={"file_name": "manual.pdf", "source": "docs/manual.pdf", "page": 1},
        )
        chunks = split_documents([doc], structured=True, chunk_size=200, chunk_overlap=20)
        assert all(c.metadata.get("file_type") == "pdf" for c in chunks)

    def test_structured_false_uses_generic_splitter(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="# Heading\n\n" + "Conteúdo. " * 50,
            metadata={"file_name": "doc.md", "source": "docs/doc.md", "page": None},
        )
        chunks = split_documents([doc], structured=False, chunk_size=200, chunk_overlap=20)
        # All chunks should have chunk_id (via _enrich_chunk_metadata)
        assert all("chunk_id" in c.metadata for c in chunks)

    def test_all_chunks_have_required_fields(self):
        from docops.ingestion.splitter import split_documents

        doc = Document(
            page_content="# Seção\n\nTexto importante para indexar.",
            metadata={"file_name": "arq.md", "source": "docs/arq.md", "page": None},
        )
        chunks = split_documents([doc], structured=True)
        required = {
            "chunk_id",
            "chunk_index",
            "doc_id",
            "source_path",
            "file_type",
            "page_start",
            "page_end",
            "section_title",
            "section_path",
        }
        for c in chunks:
            missing = required - c.metadata.keys()
            assert not missing, f"Missing metadata fields: {missing}"

    def test_empty_input_returns_empty(self):
        from docops.ingestion.splitter import split_documents

        assert split_documents([]) == []
