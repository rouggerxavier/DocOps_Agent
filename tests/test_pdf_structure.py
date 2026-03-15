"""Tests for PDF structure inference (docops.ingestion.pdf_structure)."""

import pytest
from langchain_core.documents import Document

from docops.ingestion.pdf_structure import (
    infer_pdf_structure,
    extract_pdf_outline,
    _is_valid_section_label,
    _is_title_like,
    _is_toc_page,
    _extract_toc_topics,
    _get_first_salient_line,
    _compute_lexical_distance,
)


def _make_pdf_chunk(text: str, page: int = 1, **extra_meta) -> Document:
    """Helper to create a PDF chunk with standard metadata."""
    meta = {
        "file_name": "test.pdf",
        "file_type": "pdf",
        "page": page,
        "page_start": page,
        "page_end": page,
        "section_title": "",
        "section_path": "",
        "chunk_index": page - 1,
    }
    meta.update(extra_meta)
    return Document(page_content=text, metadata=meta)


# ── Title detection tests ────────────────────────────────────────────────────

class TestTitleDetection:
    def test_numbered_heading(self):
        assert _is_title_like("1.1 Introduction to Machine Learning")

    def test_numbered_heading_deeper(self):
        assert _is_title_like("2.3.1 Decision Tree Construction")

    def test_caps_title(self):
        assert _is_title_like("ÁRVORES DE DECISÃO")

    def test_title_case(self):
        assert _is_title_like("Random Forest e Boosting")

    def test_chapter_marker_pt(self):
        assert _is_title_like("Capítulo 3 - Regularização")

    def test_chapter_marker_en(self):
        assert _is_title_like("Chapter 5 - Generalization")

    def test_not_title_sentence(self):
        # Regular sentence ending with period should not be a title.
        assert not _is_title_like("This is a regular sentence about something.")

    def test_not_title_sentence_without_period(self):
        assert not _is_title_like("The model uses entropy and pruning to build splits")

    def test_not_title_descriptive_line(self):
        assert not _is_title_like("This slide shows the architecture of the system")

    def test_not_title_long(self):
        assert not _is_title_like("A" * 130)

    def test_empty(self):
        assert not _is_title_like("")

    def test_noisy_short_label_rejected(self):
        assert _is_valid_section_label("+1 t3") is False
        assert not _is_title_like("+1 t3")


# ── TOC detection tests ──────────────────────────────────────────────────────

class TestTOCDetection:
    def test_toc_page(self):
        toc_text = (
            "1. Introduction .............. 3\n"
            "2. Methods ................... 7\n"
            "3. Results ................... 12\n"
            "4. Discussion ................ 18\n"
            "5. Conclusion ................ 22\n"
        )
        assert _is_toc_page(toc_text)

    def test_not_toc_page(self):
        regular_text = (
            "This is a regular paragraph about machine learning.\n"
            "It discusses various algorithms and their applications.\n"
            "The results show that the method is effective.\n"
        )
        assert not _is_toc_page(regular_text)

    def test_toc_topic_extraction(self):
        toc_text = (
            "1. Introduction\n"
            "1.1 Background\n"
            "2. Decision Trees\n"
            "2.1 Construction Algorithm\n"
            "3. Evaluation\n"
        )
        topics = _extract_toc_topics(toc_text)
        assert len(topics) >= 3
        titles = [t["title"] for t in topics]
        assert "Introduction" in titles
        assert "Decision Trees" in titles


# ── Structure inference tests ─────────────────────────────────────────────────

class TestPDFStructureInference:
    def test_infer_from_title_lines(self):
        """Chunks with title-like first lines should get section_title."""
        chunks = [
            _make_pdf_chunk("Introduction\nThis chapter introduces the topic of ML.", page=1),
            _make_pdf_chunk("Decision Trees\nA decision tree is a flowchart-like structure.", page=2),
            _make_pdf_chunk("Random Forests\nRandom forest is an ensemble method.", page=3),
        ]
        infer_pdf_structure(chunks)
        assert chunks[0].metadata["section_title"] == "Introduction"
        assert chunks[1].metadata["section_title"] == "Decision Trees"
        assert chunks[2].metadata["section_title"] == "Random Forests"

    def test_infer_from_numbered_headings(self):
        chunks = [
            _make_pdf_chunk("1.1 Fundamentals of Classification\nText about classification.", page=1),
            _make_pdf_chunk("1.2 Regression Analysis\nText about regression.", page=2),
            _make_pdf_chunk("2.1 Ensemble Methods\nText about ensembles.", page=3),
        ]
        infer_pdf_structure(chunks)
        assert "1.1" in chunks[0].metadata["section_title"] or "Fundamentals" in chunks[0].metadata["section_title"]
        assert chunks[2].metadata.get("section_title", "")  # Should have some title

    def test_preserves_existing_metadata(self):
        """Chunks with existing section metadata should not be overwritten."""
        chunks = [
            _make_pdf_chunk("Some text", page=1, section_title="Existing Title", section_path="Existing > Path"),
        ]
        infer_pdf_structure(chunks)
        assert chunks[0].metadata["section_title"] == "Existing Title"
        assert chunks[0].metadata["section_path"] == "Existing > Path"

    def test_cleans_meta_labeled_existing_metadata(self):
        """Leaked [meta] labels in section metadata should be replaced by inferred title."""
        chunks = [
            _make_pdf_chunk(
                "[meta] page: 5\nDecision Trees\nCore content here.",
                page=5,
                section_title="[meta] page: 5",
                section_path="[meta] page: 5",
            ),
        ]
        infer_pdf_structure(chunks)
        assert chunks[0].metadata["section_title"] == "Decision Trees"
        assert chunks[0].metadata["section_path"] == "Decision Trees"

    def test_meta_header_not_used_as_title(self):
        """Embedding [meta] header should be ignored when inferring headings."""
        chunks = [
            _make_pdf_chunk(
                "[meta] page: 3\nTAXONOMIA\nConteudo da secao.",
                page=3,
            ),
        ]
        infer_pdf_structure(chunks)
        assert chunks[0].metadata["section_title"] == "TAXONOMIA"
        assert "[meta]" not in chunks[0].metadata["section_title"].lower()

    def test_only_processes_pdf_chunks(self):
        """Non-PDF chunks should be skipped."""
        chunks = [
            Document(
                page_content="# Markdown Title\nSome content",
                metadata={"file_type": "md", "section_title": "", "section_path": ""},
            ),
        ]
        infer_pdf_structure(chunks)
        assert chunks[0].metadata["section_title"] == ""

    def test_lexical_transition_detection(self):
        """When pages have title-like first lines, they should be used as section titles."""
        chunks = [
            _make_pdf_chunk(
                "Machine Learning Algorithms\n"
                "Machine learning algorithms use data to learn patterns and make predictions. "
                "Supervised learning requires labeled training data. Classification and regression "
                "are the two main tasks in supervised machine learning.",
                page=1,
            ),
            _make_pdf_chunk(
                "Photosynthesis Overview\n"
                "Photosynthesis is the process by which plants convert sunlight into energy. "
                "Chlorophyll absorbs light in the visible spectrum. The Calvin cycle produces "
                "glucose from carbon dioxide and water in plant cells.",
                page=2,
            ),
        ]
        infer_pdf_structure(chunks, transition_threshold=0.5)
        # Both chunks have title-like first lines.
        assert chunks[0].metadata.get("section_title", "")
        assert chunks[1].metadata.get("section_title", "")
        assert chunks[0].metadata["section_title"] != chunks[1].metadata["section_title"]

    def test_toc_based_inference(self):
        """TOC pages should help infer structure for subsequent pages."""
        chunks = [
            _make_pdf_chunk(
                "1. Introduction .............. 3\n"
                "2. Methods ................... 7\n"
                "3. Results ................... 12\n"
                "4. Discussion ................ 18\n",
                page=1,
            ),
            _make_pdf_chunk("Introduction\nThis paper presents a new method for classification.", page=2),
            _make_pdf_chunk("Methods\nWe use a random forest classifier with 500 trees.", page=3),
        ]
        infer_pdf_structure(chunks)
        # TOC topics should be detected.
        assert chunks[1].metadata.get("section_title", "")
        assert chunks[2].metadata.get("section_title", "")

    def test_empty_chunks(self):
        """Empty chunk list should not raise."""
        result = infer_pdf_structure([])
        assert result == []

    def test_chapter_markers(self):
        chunks = [
            _make_pdf_chunk("Capítulo 1 - Fundamentos\nTexto sobre fundamentos.", page=1),
            _make_pdf_chunk("Capítulo 2 - Métodos\nTexto sobre métodos.", page=2),
        ]
        infer_pdf_structure(chunks)
        assert "Capítulo 1" in chunks[0].metadata["section_title"]
        assert "Capítulo 2" in chunks[1].metadata["section_title"]


# ── Outline extraction tests ─────────────────────────────────────────────────

class TestExtractPDFOutline:
    def test_outline_from_inferred_structure(self):
        chunks = [
            _make_pdf_chunk("Introduction\nIntro content.", page=1),
            _make_pdf_chunk("Still intro content continues.", page=2),
            _make_pdf_chunk("Methods\nMethod details.", page=3),
            _make_pdf_chunk("Results\nResult details.", page=4),
        ]
        infer_pdf_structure(chunks)
        outline = extract_pdf_outline(chunks)
        assert len(outline) >= 2  # At least Introduction and Methods/Results
        titles = [e["title"] for e in outline]
        assert any("Introduction" in t for t in titles)

    def test_outline_empty_chunks(self):
        outline = extract_pdf_outline([])
        assert outline == []

    def test_outline_ignores_meta_section_title(self):
        chunks = [
            _make_pdf_chunk("Conteudo", page=1, section_title="[meta] page: 1", section_path="[meta] page: 1"),
            _make_pdf_chunk("Methods\nDetails", page=2, section_title="Methods", section_path="Methods"),
        ]
        outline = extract_pdf_outline(chunks)
        titles = [e["title"] for e in outline]
        assert all("[meta]" not in t.lower() for t in titles)


# ── Helper function tests ────────────────────────────────────────────────────

class TestHelpers:
    def test_first_salient_line_skips_numbers(self):
        text = "42\n\nImportant Title\nContent here."
        line = _get_first_salient_line(text)
        assert line == "Important Title"

    def test_first_salient_line_skips_slide_numbers(self):
        text = "Slide 5\nActual Title\nContent."
        line = _get_first_salient_line(text)
        assert line == "Actual Title"

    def test_first_salient_line_skips_meta_header(self):
        text = "[meta] page: 9\nUseful Heading\nContent."
        line = _get_first_salient_line(text)
        assert line == "Useful Heading"

    def test_lexical_distance_identical(self):
        d = _compute_lexical_distance("hello world foo bar", "hello world foo bar")
        assert d < 0.1

    def test_lexical_distance_different(self):
        d = _compute_lexical_distance(
            "machine learning algorithm prediction model",
            "photosynthesis chlorophyll sunlight energy plants",
        )
        assert d > 0.8

    def test_lexical_distance_empty(self):
        assert _compute_lexical_distance("", "hello") == 1.0
        assert _compute_lexical_distance("hello", "") == 1.0
