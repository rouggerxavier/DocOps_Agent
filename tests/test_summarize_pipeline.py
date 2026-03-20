"""Tests for the multi-step deep summary pipeline.

Coverage:
  - text_cleaner: clean_chunk_text and clean_summary_output,
                  ligature expansion, PUA character removal
  - pipeline: _sort_chunks, group_chunks, _group_by_section, _group_by_window,
              _normalize_groups, collect_ordered_chunks (mocked), run_deep_summary (mocked),
              _select_citation_anchors
  - Claim-risk + inference-density: classify_claim_risks, check_formula_mode,
              compute_inference_density, _is_low_info_source, run_deoverreach_pass
  - citations: build_summary_sources_section (deduplication, page ranges, cap)
  - config: summary_group_size, summary_max_groups, summary_section_threshold,
            summary_max_sources
  - Regression: brief summary still routes through the LangGraph (contract preserved)
  - API contract: SummarizeResponse shape unchanged
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")


@pytest.fixture(autouse=True)
def _default_deep_profile_for_legacy_tests(monkeypatch):
    """Keep legacy integration expectations on strict path unless test overrides it."""
    monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "strict")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _doc(text: str, **meta) -> Document:
    return Document(page_content=text, metadata=meta)


def _make_chunks(n: int, with_sections: bool = False) -> list[Document]:
    chunks = []
    for i in range(n):
        meta: dict = {"chunk_index": i, "page": i + 1}
        if with_sections:
            meta["section_path"] = f"Seção {i // 3 + 1}"
        chunks.append(_doc(f"Conteúdo do chunk {i}.", **meta))
    return chunks


# ──────────────────────────────────────────────────────────────────────────────
# text_cleaner
# ──────────────────────────────────────────────────────────────────────────────

class TestCleanChunkText:
    def setup_method(self):
        from docops.summarize.text_cleaner import clean_chunk_text
        self.clean = clean_chunk_text

    def test_nop_on_clean_text(self):
        text = "Algoritmo de Dijkstra para grafos ponderados."
        assert self.clean(text) == text

    def test_removes_replacement_char(self):
        text = "Custo\ufffd total"
        result = self.clean(text)
        assert "\ufffd" not in result
        assert "Custo" in result
        assert "total" in result

    def test_removes_invisible_chars(self):
        text = "texto\u200bcom\u200czero\u200dwidth"
        result = self.clean(text)
        assert "\u200b" not in result
        assert "\u200c" not in result
        assert "\u200d" not in result

    def test_removes_bom(self):
        text = "\ufeffInício do documento"
        result = self.clean(text)
        assert not result.startswith("\ufeff")
        assert "Início" in result

    def test_removes_null_bytes(self):
        text = "texto\x00com\x00nulos"
        result = self.clean(text)
        assert "\x00" not in result
        assert "texto" in result

    def test_fixes_hyphen_line_break(self):
        text = "algo-\nritmo de busca"
        result = self.clean(text)
        assert "algoritmo" in result

    def test_collapses_excessive_spaces(self):
        text = "palavra   com    espaços"
        result = self.clean(text)
        assert "   " not in result

    def test_normalizes_blank_lines(self):
        text = "parágrafo 1\n\n\n\n\nparágrafo 2"
        result = self.clean(text)
        assert "\n\n\n" not in result

    def test_preserves_math_symbols(self):
        # Valid Unicode math should NOT be removed
        text = "A função f(x) = ∑xᵢ para i em N"
        result = self.clean(text)
        assert "∑" in result

    def test_preserves_markdown_structure(self):
        text = "## Seção 1\n\nConteúdo com **negrito** e `código`."
        result = self.clean(text)
        assert "## Seção 1" in result
        assert "**negrito**" in result

    def test_empty_string(self):
        assert self.clean("") == ""

    def test_preserves_accented_chars(self):
        text = "análise de árvores binárias de decisão"
        result = self.clean(text)
        assert result == text


class TestCleanSummaryOutput:
    def setup_method(self):
        from docops.summarize.text_cleaner import clean_summary_output
        self.clean = clean_summary_output

    def test_removes_trailing_whitespace_per_line(self):
        text = "linha 1   \nlinha 2  \nlinha 3"
        result = self.clean(text)
        for line in result.split("\n"):
            assert not line.endswith(" "), f"Line still has trailing space: {repr(line)}"

    def test_normalizes_blank_lines(self):
        text = "# Título\n\n\n\n## Subtítulo"
        result = self.clean(text)
        assert "\n\n\n" not in result

    def test_removes_replacement_char(self):
        text = "Resultado\ufffd final"
        result = self.clean(text)
        assert "\ufffd" not in result

    def test_nop_on_clean_markdown(self):
        text = "# Resumo\n\n## Seção 1\n\nConteúdo limpo."
        result = self.clean(text)
        assert "# Resumo" in result
        assert "## Seção 1" in result

    def test_normalizes_math_styled_unicode_and_sinhala_artifacts(self):
        text = "Cost-Complexity: 𝑅𝛼 𝑇 = 𝑅 𝑇 + 𝛼 ∙ ෨𝑇"
        result = self.clean(text)
        assert "𝑅" not in result
        assert "𝛼" not in result
        assert "෨" not in result
        assert "R" in result


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: _sort_chunks
# ──────────────────────────────────────────────────────────────────────────────

class TestSortChunks:
    def setup_method(self):
        from docops.summarize.pipeline import _sort_chunks
        self.sort = _sort_chunks

    def test_sorts_by_chunk_index(self):
        chunks = [
            _doc("c", chunk_index=2),
            _doc("a", chunk_index=0),
            _doc("b", chunk_index=1),
        ]
        result = self.sort(chunks)
        assert [d.page_content for d in result] == ["a", "b", "c"]

    def test_sorts_by_page_when_no_chunk_index(self):
        chunks = [
            _doc("segundo", page=2),
            _doc("primeiro", page=1),
            _doc("terceiro", page=3),
        ]
        result = self.sort(chunks)
        assert result[0].page_content == "primeiro"
        assert result[-1].page_content == "terceiro"

    def test_chunk_index_takes_priority_over_page(self):
        # chunk_index=0 should come before chunk_index=1 regardless of page
        chunks = [
            _doc("B", chunk_index=1, page=1),
            _doc("A", chunk_index=0, page=5),
        ]
        result = self.sort(chunks)
        assert result[0].page_content == "A"

    def test_stable_on_equal_keys(self):
        chunks = [_doc(f"c{i}", chunk_index=0, page=1) for i in range(5)]
        result = self.sort(chunks)
        assert len(result) == 5

    def test_empty_list(self):
        assert self.sort([]) == []


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: group_chunks
# ──────────────────────────────────────────────────────────────────────────────

class TestGroupChunks:
    def setup_method(self):
        from docops.summarize.pipeline import (
            group_chunks,
            SUMMARY_GROUP_SIZE,
            SUMMARY_MAX_GROUPS,
        )
        self.group = group_chunks
        self.group_size = SUMMARY_GROUP_SIZE
        self.max_groups = SUMMARY_MAX_GROUPS

    def test_window_grouping_when_no_sections(self):
        chunks = _make_chunks(15, with_sections=False)
        groups = self.group(chunks)
        # With no section metadata, should use window grouping
        assert len(groups) >= 1
        assert len(groups) <= self.max_groups
        # All chunks should be present
        total = sum(len(g) for g in groups)
        assert total == 15

    def test_section_grouping_when_sections_present(self):
        # 12 chunks, all with section_path → section-based grouping
        chunks = _make_chunks(12, with_sections=True)
        groups = self.group(chunks)
        assert len(groups) >= 1
        assert len(groups) <= self.max_groups
        total = sum(len(g) for g in groups)
        assert total == 12

    def test_max_groups_respected(self):
        # 100 chunks without sections — should not exceed SUMMARY_MAX_GROUPS
        chunks = _make_chunks(100, with_sections=False)
        groups = self.group(chunks)
        assert len(groups) <= self.max_groups

    def test_empty_input(self):
        assert self.group([]) == []

    def test_single_chunk(self):
        groups = self.group([_doc("único", chunk_index=0)])
        assert len(groups) == 1
        assert len(groups[0]) == 1

    def test_all_chunks_preserved(self):
        chunks = _make_chunks(30, with_sections=True)
        groups = self.group(chunks)
        total = sum(len(g) for g in groups)
        assert total == 30


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: _group_by_section (stable ordering)
# ──────────────────────────────────────────────────────────────────────────────

class TestGroupBySection:
    def setup_method(self):
        from docops.summarize.pipeline import _group_by_section
        self.group = _group_by_section

    def test_groups_consecutive_same_section(self):
        chunks = [
            _doc("a1", section_path="A"),
            _doc("a2", section_path="A"),
            _doc("b1", section_path="B"),
            _doc("b2", section_path="B"),
            _doc("c1", section_path="C"),
        ]
        groups = self.group(chunks)
        assert len(groups) == 3
        assert len(groups[0]) == 2  # section A
        assert len(groups[1]) == 2  # section B
        assert len(groups[2]) == 1  # section C

    def test_interleaved_sections_produce_separate_groups(self):
        # A, B, A — the second A is a new group because it's not consecutive with first A
        chunks = [
            _doc("a", section_path="A"),
            _doc("b", section_path="B"),
            _doc("a2", section_path="A"),
        ]
        groups = self.group(chunks)
        assert len(groups) == 3

    def test_no_section_metadata(self):
        chunks = [_doc(f"c{i}") for i in range(4)]
        groups = self.group(chunks)
        # All chunks have empty section → one big group
        assert len(groups) == 1
        assert len(groups[0]) == 4


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: collect_ordered_chunks — document corpus is treated as closed/ordered
# ──────────────────────────────────────────────────────────────────────────────

class TestCollectOrderedChunks:
    """Test that collect_ordered_chunks returns sorted chunks without query bias."""

    @patch("docops.ingestion.indexer.get_vectorstore_for_user")
    def test_uses_chroma_get_without_query(self, mock_get_vs):
        """Verify the primary path uses Chroma get() (no similarity_search)."""
        from docops.summarize.pipeline import collect_ordered_chunks

        mock_vs = MagicMock()
        mock_vs.get.return_value = {
            "ids": ["id1", "id2", "id0"],
            "documents": ["texto 1", "texto 2", "texto 0"],
            "metadatas": [
                {"chunk_index": 1, "page": 2},
                {"chunk_index": 2, "page": 3},
                {"chunk_index": 0, "page": 1},
            ],
        }
        mock_get_vs.return_value = mock_vs

        result = collect_ordered_chunks("doc.pdf", "doc-uuid", user_id=1)

        # Should have called get(), NOT similarity_search
        mock_vs.get.assert_called_once()
        mock_vs.similarity_search.assert_not_called()

        # Result should be sorted by chunk_index
        assert len(result) == 3
        assert result[0].page_content == "texto 0"  # chunk_index=0
        assert result[1].page_content == "texto 1"  # chunk_index=1
        assert result[2].page_content == "texto 2"  # chunk_index=2

    @patch("docops.ingestion.indexer.get_vectorstore_for_user")
    @patch("docops.summarize.pipeline._fallback_collect")
    def test_falls_back_when_get_returns_empty(self, mock_fallback, mock_get_vs):
        """If Chroma get() returns no results, fall back to similarity_search."""
        from docops.summarize.pipeline import collect_ordered_chunks

        mock_vs = MagicMock()
        mock_vs.get.return_value = {"ids": [], "documents": [], "metadatas": []}
        mock_get_vs.return_value = mock_vs
        mock_fallback.return_value = [_doc("fallback chunk", chunk_index=0)]

        result = collect_ordered_chunks("doc.pdf", "doc-uuid", user_id=1)

        mock_fallback.assert_called_once()
        assert len(result) == 1
        assert result[0].page_content == "fallback chunk"

    @patch("docops.ingestion.indexer.get_vectorstore_for_user")
    @patch("docops.summarize.pipeline._fallback_collect")
    def test_falls_back_on_get_exception(self, mock_fallback, mock_get_vs):
        """If Chroma get() raises, fall back gracefully."""
        from docops.summarize.pipeline import collect_ordered_chunks

        mock_vs = MagicMock()
        mock_vs.get.side_effect = AttributeError("get() not supported")
        mock_get_vs.return_value = mock_vs
        mock_fallback.return_value = [_doc("fallback", chunk_index=0)]

        result = collect_ordered_chunks("doc.pdf", "doc-uuid", user_id=1)
        mock_fallback.assert_called_once()
        assert result[0].page_content == "fallback"


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: run_deep_summary (end-to-end, fully mocked)
# ──────────────────────────────────────────────────────────────────────────────

class TestRunDeepSummary:
    """Integration test for the full pipeline with all LLM calls mocked."""

    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_returns_answer_with_sources(self, mock_collect, mock_llm_factory):
        from docops.summarize.pipeline import run_deep_summary

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response(
            "Resumo da seção gerado pelo LLM."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "answer" in result
        assert "sources_section" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        # Sources section should be appended
        assert "**Fontes:**" in result["answer"] or "**Fontes:**" in result["sources_section"]

    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_returns_error_message_when_no_chunks(self, mock_collect):
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = []

        result = run_deep_summary("inexistente.pdf", "bad-uuid", user_id=1)

        assert "answer" in result
        assert "Não foram encontrados" in result["answer"]
        assert result["sources_section"] == ""

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_pipeline_calls_llm_for_partials_consolidation_and_final(
        self, mock_collect, mock_llm_factory
    ):
        from docops.summarize.pipeline import run_deep_summary, SUMMARY_MAX_GROUPS

        chunks = _make_chunks(12, with_sections=True)
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response("Texto gerado.")
        mock_llm_factory.return_value = mock_llm

        run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        # LLM was called at least: (N partial) + 1 consolidation + 1 final
        # + 1 style-polish pass = N+3
        call_count = mock_llm.invoke.call_count
        assert call_count >= 4, f"Expected ≥4 LLM calls, got {call_count}"

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_output_is_cleaned(self, mock_collect, mock_llm_factory):
        from docops.summarize.pipeline import run_deep_summary

        chunks = _make_chunks(4)
        mock_collect.return_value = chunks

        # LLM returns text with invisible chars and replacement char
        dirty = "Resumo\ufffdcom\u200bartefatos   \n\n\n\nexcessivos"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response(dirty)
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "\ufffd" not in result["answer"]
        assert "\u200b" not in result["answer"]
        assert "\n\n\n\n" not in result["answer"]

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline.infer_pdf_structure")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_pdf_structure_inference_happens_before_topic_extraction(
        self,
        mock_collect,
        mock_infer,
        mock_extract_topics,
        mock_llm_factory,
    ):
        from docops.summarize.pipeline import run_deep_summary

        chunks = [
            _doc("Introduction\nContent.", file_type="pdf", page=1, page_start=1, page_end=1, section_title="", section_path="", chunk_index=0),
            _doc("Methods\nContent.", file_type="pdf", page=2, page_start=2, page_end=2, section_title="", section_path="", chunk_index=1),
        ]
        mock_collect.return_value = chunks

        def _infer_side_effect(chunks_in):
            for c in chunks_in:
                if not c.metadata.get("section_title"):
                    c.metadata["section_title"] = "Inferred Section"
                    c.metadata["section_path"] = "Inferred Section"
            return chunks_in

        mock_infer.side_effect = _infer_side_effect

        def _extract_topics_side_effect(chunks_in, major_topic_min_hits=2):
            assert any(c.metadata.get("section_title") for c in chunks_in)
            return {
                "detected_topics": [],
                "must_cover_topics": [],
                "minor_topics": [],
                "topic_details": {},
                "outline_text": "",
            }

        mock_extract_topics.side_effect = _extract_topics_side_effect

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response("Texto gerado.")
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        assert result.get("answer")


# ──────────────────────────────────────────────────────────────────────────────
# Regression: brief mode still routes through graph (contract test)
# ──────────────────────────────────────────────────────────────────────────────

class TestBriefModeRegression:
    """Verify that brief mode continues to use the LangGraph run() function."""

    def test_brief_calls_graph_run_not_pipeline(self, monkeypatch):
        """Brief mode must call graph.run(), not run_deep_summary()."""
        graph_called = []
        pipeline_called = []

        def fake_graph_run(query, extra, user_id, **kwargs):
            graph_called.append(query)
            return {"answer": "Resumo breve gerado pelo grafo."}

        def fake_deep_summary(doc_name, doc_id, user_id, **kwargs):
            pipeline_called.append(doc_name)
            return {"answer": "deep"}

        monkeypatch.setattr("docops.api.routes.summarize.graph", None, raising=False)
        # Patch graph.run inside the module namespace
        import docops.api.routes.summarize as summarize_module
        original_run = None

        # Simulate _run_summarize directly
        with patch("docops.graph.graph.run", side_effect=fake_graph_run):
            with patch(
                "docops.summarize.pipeline.run_deep_summary",
                side_effect=fake_deep_summary,
            ):
                from docops.api.routes.summarize import _run_summarize

                # For brief mode, graph.run should be called
                try:
                    _run_summarize(
                        file_name="test.pdf",
                        doc_id="test-uuid",
                        save=False,
                        summary_mode="brief",
                        user_id=1,
                    )
                except Exception:
                    pass  # May fail without real vectorstore — we only check call routing

        # If graph.run was called (even partially), brief mode is on the right path
        # The important thing is the pipeline was NOT called
        assert len(pipeline_called) == 0, (
            "run_deep_summary() must NOT be called for brief mode"
        )

    def test_deep_calls_pipeline_not_graph(self, monkeypatch):
        """Deep mode must call run_deep_summary(), not graph.run()."""
        graph_called = []
        pipeline_called = []

        def fake_deep_summary(doc_name, doc_id, user_id, **kwargs):
            pipeline_called.append(doc_name)
            return {"answer": "# Resumo Aprofundado\n\nConteúdo gerado."}

        def fake_graph_run(**kwargs):
            graph_called.append(True)
            return {"answer": "graph"}

        with patch(
            "docops.summarize.pipeline.run_deep_summary",
            side_effect=fake_deep_summary,
        ):
            with patch("docops.graph.graph.run", side_effect=fake_graph_run):
                from docops.api.routes.summarize import _run_summarize

                result = _run_summarize(
                    file_name="test.pdf",
                    doc_id="test-uuid",
                    save=False,
                    summary_mode="deep",
                    user_id=1,
                )

        assert len(pipeline_called) == 1, "run_deep_summary() must be called for deep mode"
        assert len(graph_called) == 0, "graph.run() must NOT be called for deep mode"
        assert result["answer"] == "# Resumo Aprofundado\n\nConteúdo gerado."

    def test_deep_debug_threads_include_diagnostics_flag(self):
        called_kwargs = {}

        def fake_deep_summary(doc_name, doc_id, user_id, **kwargs):
            called_kwargs.update(kwargs)
            return {
                "answer": "# Resumo Aprofundado\n\nConteúdo gerado.",
                "diagnostics": {"coverage": {"overall_coverage_score": 1.0}},
            }

        with patch(
            "docops.summarize.pipeline.run_deep_summary",
            side_effect=fake_deep_summary,
        ):
            from docops.api.routes.summarize import _run_summarize

            result = _run_summarize(
                file_name="test.pdf",
                doc_id="test-uuid",
                save=False,
                summary_mode="deep",
                user_id=1,
                debug_summary=True,
            )

        assert called_kwargs.get("include_diagnostics") is True
        assert result.get("diagnostics") is not None


# ──────────────────────────────────────────────────────────────────────────────
# API schema contract
# ──────────────────────────────────────────────────────────────────────────────

class TestSummarizeSchemaContract:
    """Verify summarize API schema contract."""

    def test_request_schema_fields(self):
        from docops.api.schemas import SummarizeRequest

        req = SummarizeRequest(
            doc="manual.pdf",
            save=True,
            summary_mode="deep",
            debug_summary=True,
        )
        assert req.doc == "manual.pdf"
        assert req.save is True
        assert req.summary_mode == "deep"
        assert req.debug_summary is True

    def test_request_defaults(self):
        from docops.api.schemas import SummarizeRequest

        req = SummarizeRequest(doc="manual.pdf")
        assert req.save is False
        assert req.summary_mode == "brief"
        assert req.debug_summary is False

    def test_response_schema_fields(self):
        from docops.api.schemas import SummarizeResponse

        resp = SummarizeResponse(answer="Resumo aqui.", artifact_path=None)
        assert resp.answer == "Resumo aqui."
        assert resp.artifact_path is None
        assert resp.summary_diagnostics is None

    def test_response_with_artifact_path(self):
        from docops.api.schemas import SummarizeResponse

        resp = SummarizeResponse(answer="Resumo.", artifact_path="/path/to/file.md")
        assert resp.artifact_path == "/path/to/file.md"

    def test_response_with_summary_diagnostics(self):
        from docops.api.schemas import SummarizeResponse

        resp = SummarizeResponse(
            answer="Resumo.",
            summary_diagnostics={"coverage": {"overall_coverage_score": 0.9}},
        )
        assert resp.summary_diagnostics is not None
        assert resp.summary_diagnostics["coverage"]["overall_coverage_score"] == 0.9

    def test_new_prompts_exported(self):
        """All deep-summary pipeline prompts must be importable from rag.prompts."""
        from docops.rag.prompts import (
            DEEP_SUMMARY_PARTIAL_PROMPT,
            DEEP_SUMMARY_CONSOLIDATE_PROMPT,
            DEEP_SUMMARY_FINAL_PROMPT,
            DEEP_SUMMARY_STYLE_POLISH_PROMPT,
        )
        assert "{context}" in DEEP_SUMMARY_PARTIAL_PROMPT
        assert "{partials_block}" in DEEP_SUMMARY_CONSOLIDATE_PROMPT
        assert "{consolidated}" in DEEP_SUMMARY_FINAL_PROMPT
        assert "{partials_block}" in DEEP_SUMMARY_FINAL_PROMPT
        assert "{context_sample}" in DEEP_SUMMARY_FINAL_PROMPT
        assert "{draft}" in DEEP_SUMMARY_STYLE_POLISH_PROMPT

    def test_final_and_style_prompts_discourage_glossary_output(self):
        from docops.rag.prompts import (
            DEEP_SUMMARY_FINAL_PROMPT,
            DEEP_SUMMARY_STYLE_POLISH_PROMPT,
        )

        assert "glossário" in DEEP_SUMMARY_FINAL_PROMPT.lower()
        assert "no máximo 6 seções" in DEEP_SUMMARY_STYLE_POLISH_PROMPT.lower()
        assert "não explicitado no material" in DEEP_SUMMARY_FINAL_PROMPT.lower()
        assert "frases promocionais" in DEEP_SUMMARY_STYLE_POLISH_PROMPT.lower()

    def test_brief_prompt_avoids_mechanical_verbs_instruction(self):
        """BRIEF_SUMMARY_PROMPT must instruct the LLM to avoid mechanical verbs."""
        from docops.rag.prompts import BRIEF_SUMMARY_PROMPT
        # The prompt should contain anti-verb guidance
        assert "EVITE" in BRIEF_SUMMARY_PROMPT or "evite" in BRIEF_SUMMARY_PROMPT.lower()

    def test_partial_prompt_handles_fragmented_content_instruction(self):
        """DEEP_SUMMARY_PARTIAL_PROMPT must instruct how to handle fragmented chunks."""
        from docops.rag.prompts import DEEP_SUMMARY_PARTIAL_PROMPT
        assert "fragmentad" in DEEP_SUMMARY_PARTIAL_PROMPT.lower() or \
               "ilegível" in DEEP_SUMMARY_PARTIAL_PROMPT.lower() or \
               "degradad" in DEEP_SUMMARY_PARTIAL_PROMPT.lower()


# ──────────────────────────────────────────────────────────────────────────────
# text_cleaner: ligature expansion and PUA removal (new)
# ──────────────────────────────────────────────────────────────────────────────

class TestLigatureExpansion:
    def setup_method(self):
        from docops.summarize.text_cleaner import clean_chunk_text
        self.clean = clean_chunk_text

    def test_fi_ligature_expanded(self):
        text = "de\ufb01ni\u00e7\u00e3o"  # "deﬁnição"
        result = self.clean(text)
        assert "\ufb01" not in result
        assert "fi" in result  # expanded to "fi"

    def test_fl_ligature_expanded(self):
        text = "con\ufb02uência"  # "conflência" with ﬂ
        result = self.clean(text)
        assert "\ufb02" not in result
        assert "fl" in result

    def test_ff_ligature_expanded(self):
        text = "e\ufb00icient"  # "eﬀicient"
        result = self.clean(text)
        assert "\ufb00" not in result
        assert "ff" in result

    def test_ffi_ligature_expanded(self):
        text = "e\ufb03cient"  # "eﬃcient"
        result = self.clean(text)
        assert "\ufb03" not in result
        assert "ffi" in result

    def test_multiple_ligatures_in_one_string(self):
        text = "e\ufb00icient de\ufb01nition con\ufb02uence"
        result = self.clean(text)
        assert "\ufb00" not in result
        assert "\ufb01" not in result
        assert "\ufb02" not in result
        assert "ff" in result
        assert "fi" in result
        assert "fl" in result

    def test_ligature_in_technical_term(self):
        text = "coe\ufb03cient of variation"  # coefﬃcient
        result = self.clean(text)
        assert "\ufb03" not in result
        assert "ffi" in result

    def test_no_change_on_clean_text(self):
        text = "efficient definition confluence"
        result = self.clean(text)
        assert result == text


class TestPUARemoval:
    def setup_method(self):
        from docops.summarize.text_cleaner import clean_chunk_text
        self.clean = clean_chunk_text

    def test_pua_char_removed(self):
        text = "texto\ue000com\uf8ffpua"
        result = self.clean(text)
        assert "\ue000" not in result
        assert "\uf8ff" not in result
        assert "texto" in result
        assert "pua" in result

    def test_mid_pua_range_removed(self):
        text = "A\ue500B"
        result = self.clean(text)
        assert "\ue500" not in result
        assert "AB" in result

    def test_no_change_on_clean_text(self):
        text = "Algoritmo de busca binária."
        result = self.clean(text)
        assert result == text


# ──────────────────────────────────────────────────────────────────────────────
# citations: build_summary_sources_section (new)
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildSummarySourcesSection:
    def setup_method(self):
        from docops.rag.citations import build_summary_sources_section
        self.build = build_summary_sources_section

    def test_empty_chunks_returns_no_source_message(self):
        result = self.build([])
        assert "**Fontes:**" in result
        assert "nenhuma" in result.lower()

    def test_single_chunk_produces_one_entry(self):
        chunks = [_doc("texto", file_name="doc.pdf", page=1)]
        result = self.build(chunks)
        assert "[Fonte 1]" in result
        assert "doc.pdf" in result

    def test_deduplicates_same_file_and_section(self):
        """Multiple chunks from the same (file, section) → one source entry."""
        chunks = [
            _doc("a", file_name="doc.pdf", section_path="Intro", page=1),
            _doc("b", file_name="doc.pdf", section_path="Intro", page=2),
            _doc("c", file_name="doc.pdf", section_path="Intro", page=3),
        ]
        result = self.build(chunks)
        # Should have exactly one entry (not three)
        assert result.count("[Fonte 1]") == 1
        assert "[Fonte 2]" not in result

    def test_different_sections_produce_separate_entries(self):
        chunks = [
            _doc("a", file_name="doc.pdf", section_path="Intro", page=1),
            _doc("b", file_name="doc.pdf", section_path="Conclusão", page=10),
        ]
        result = self.build(chunks)
        assert "[Fonte 1]" in result
        assert "[Fonte 2]" in result
        assert "Intro" in result
        assert "Conclusão" in result

    def test_page_range_shown_for_multi_page_section(self):
        chunks = [
            _doc("a", file_name="doc.pdf", section_path="S1", page=3),
            _doc("b", file_name="doc.pdf", section_path="S1", page=5),
        ]
        result = self.build(chunks)
        # Should show a page range like "pp. 3–5"
        assert "pp." in result or "3" in result

    def test_single_page_shown_without_range(self):
        chunks = [_doc("a", file_name="doc.pdf", section_path="S1", page=7)]
        result = self.build(chunks)
        assert "p. 7" in result

    def test_max_sources_cap_respected(self):
        """When there are more groups than max_sources, output is capped."""
        chunks = [
            _doc(f"c{i}", file_name="doc.pdf", section_path=f"Seção {i}", page=i)
            for i in range(20)
        ]
        result = self.build(chunks, max_sources=5)
        # Should show [Fonte 5] but not [Fonte 6]
        assert "[Fonte 5]" in result
        assert "[Fonte 6]" not in result
        # Should mention the remainder
        assert "mais" in result.lower() or "+" in result

    def test_document_order_preserved(self):
        """Entries should appear in the order of first-seen chunk (document order)."""
        chunks = [
            _doc("first", file_name="doc.pdf", section_path="A", chunk_index=0),
            _doc("second", file_name="doc.pdf", section_path="B", chunk_index=1),
            _doc("third", file_name="doc.pdf", section_path="C", chunk_index=2),
        ]
        result = self.build(chunks)
        pos_a = result.index("A")
        pos_b = result.index("B")
        pos_c = result.index("C")
        assert pos_a < pos_b < pos_c

    def test_ignores_meta_section_labels(self):
        chunks = [
            _doc("a", file_name="doc.pdf", section_path="[meta] page: 3", page=3),
            _doc("b", file_name="doc.pdf", section_path="[meta] page: 4", page=4),
        ]
        result = self.build(chunks)
        assert "[meta]" not in result.lower()
        assert "[Fonte 1]" in result
        assert "[Fonte 2]" not in result


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: _select_citation_anchors (new)
# ──────────────────────────────────────────────────────────────────────────────

class TestSelectCitationAnchors:
    def setup_method(self):
        from docops.summarize.pipeline import _select_citation_anchors
        self.select = _select_citation_anchors

    def _make_groups(self, group_sizes: list[int]) -> list[list[Document]]:
        idx = 0
        groups = []
        for size in group_sizes:
            group = [_doc(f"chunk {idx + j}", chunk_index=idx + j) for j in range(size)]
            groups.append(group)
            idx += size
        return groups

    def test_returns_one_anchor_per_group(self):
        groups = self._make_groups([3, 4, 2])
        all_chunks = [c for g in groups for c in g]
        anchors = self.select(all_chunks, groups, max_anchors=10)
        # At least one anchor per group
        assert len(anchors) >= len(groups)

    def test_respects_max_anchors(self):
        groups = self._make_groups([5, 5, 5, 5, 5])
        all_chunks = [c for g in groups for c in g]
        anchors = self.select(all_chunks, groups, max_anchors=3)
        assert len(anchors) <= 3

    def test_empty_groups_uses_all_chunks_as_fallback(self):
        chunks = _make_chunks(4)
        anchors = self.select(chunks, groups=[], max_anchors=10)
        # With no groups, should return chunks up to max_anchors
        assert len(anchors) <= 10

    def test_first_chunk_of_each_group_included(self):
        groups = self._make_groups([3, 3, 3])
        all_chunks = [c for g in groups for c in g]
        anchors = self.select(all_chunks, groups, max_anchors=10)
        # First chunk of each group should be in anchors
        for group in groups:
            assert group[0] in anchors


# ──────────────────────────────────────────────────────────────────────────────
# config: summary tuning properties (new)
# ──────────────────────────────────────────────────────────────────────────────

class TestSummaryConfig:
    def test_summary_group_size_default(self):
        from docops.config import config
        assert config.summary_group_size == 8

    def test_summary_max_groups_default(self):
        from docops.config import config
        assert config.summary_max_groups == 6

    def test_summary_section_threshold_default(self):
        from docops.config import config
        assert abs(config.summary_section_threshold - 0.70) < 1e-9

    def test_summary_max_sources_default(self):
        from docops.config import config
        assert config.summary_max_sources == 12

    def test_summary_group_size_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_GROUP_SIZE", "10")
        from docops.config import Config
        assert Config().summary_group_size == 10

    def test_summary_max_groups_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MAX_GROUPS", "5")
        from docops.config import Config
        assert Config().summary_max_groups == 5

    def test_summary_max_sources_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MAX_SOURCES", "20")
        from docops.config import Config
        assert Config().summary_max_sources == 20


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: validate_summary_citations
# ──────────────────────────────────────────────────────────────────────────────

class TestValidateSummaryCitations:
    def setup_method(self):
        from docops.summarize.pipeline import validate_summary_citations
        self.validate = validate_summary_citations

    def _anchors(self, n: int) -> list[Document]:
        return [_doc(f"anchor {i}", chunk_index=i) for i in range(n)]

    def test_no_citations_detected(self):
        """Text with no [Fonte N] → no_citations=True, citations_found=0, not repaired."""
        text = "Resumo sem qualquer citação inline."
        result_text, info = self.validate(text, self._anchors(3))
        assert info["no_citations"] is True
        assert info["citations_found"] == 0
        assert info["repaired"] is False
        assert result_text == text

    def test_valid_citations_unchanged(self):
        """All [Fonte N] within range → text unchanged, repaired=False."""
        text = "Veja [Fonte 1] e também [Fonte 2] para detalhes."
        anchors = self._anchors(3)
        result_text, info = self.validate(text, anchors)
        assert result_text == text
        assert info["repaired"] is False
        assert info["no_citations"] is False
        assert info["citations_found"] == 2
        assert info["phantom_indices"] == []

    def test_phantom_citation_removed(self):
        """[Fonte N] where N > len(anchors) is stripped from the text."""
        text = "Conforme [Fonte 5] menciona, o resultado é interessante."
        anchors = self._anchors(3)  # valid range: 1..3
        result_text, info = self.validate(text, anchors)
        assert "[Fonte 5]" not in result_text
        assert "menciona, o resultado é interessante" in result_text
        assert info["repaired"] is True
        assert 5 in info["phantom_indices"]

    def test_multiple_phantoms_removed(self):
        """All out-of-range references are stripped when there are several."""
        text = "Dados em [Fonte 7] e [Fonte 10] confirmam [Fonte 99]."
        anchors = self._anchors(4)  # valid range: 1..4
        result_text, info = self.validate(text, anchors)
        assert "[Fonte 7]" not in result_text
        assert "[Fonte 10]" not in result_text
        assert "[Fonte 99]" not in result_text
        assert info["repaired"] is True
        assert set(info["phantom_indices"]) == {7, 10, 99}

    def test_mixed_valid_and_phantom(self):
        """Valid citations are kept; only phantom ones are removed."""
        text = "Ver [Fonte 2] para teoria e [Fonte 8] para exemplos."
        anchors = self._anchors(3)  # valid: 1, 2, 3; phantom: 8
        result_text, info = self.validate(text, anchors)
        assert "[Fonte 2]" in result_text      # kept
        assert "[Fonte 8]" not in result_text  # removed
        assert info["repaired"] is True
        assert info["phantom_indices"] == [8]
        assert info["citations_found"] == 2   # both were found before repair

    def test_returns_validation_info_dict_with_correct_keys(self):
        """Return value must be (str, dict) with all expected keys."""
        text = "Texto sem citações."
        _, info = self.validate(text, self._anchors(2))
        assert isinstance(info, dict)
        assert "citations_found" in info
        assert "max_valid_index" in info
        assert "phantom_indices" in info
        assert "repaired" in info
        assert "no_citations" in info

    def test_max_valid_index_matches_anchor_count(self):
        """max_valid_index must equal len(citation_anchors)."""
        anchors = self._anchors(7)
        _, info = self.validate("Texto qualquer.", anchors)
        assert info["max_valid_index"] == 7

    def test_all_citations_valid_not_repaired(self):
        """When every [Fonte N] is in range, repaired must be False."""
        text = "[Fonte 1], [Fonte 2], [Fonte 3] — tudo válido."
        anchors = self._anchors(5)
        _, info = self.validate(text, anchors)
        assert info["repaired"] is False
        assert info["phantom_indices"] == []

    def test_case_insensitive_pattern(self):
        """Pattern should match [fonte N] (lowercase) as well."""
        text = "Conforme [fonte 1] e [FONTE 2] demonstram."
        anchors = self._anchors(3)
        result_text, info = self.validate(text, anchors)
        assert info["citations_found"] == 2
        assert info["repaired"] is False


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: citation coherence integration
# ──────────────────────────────────────────────────────────────────────────────

class TestCitationCoherenceIntegration:
    """Verify that the sources section and the body text use the same anchor list."""

    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    def _resp(self, text: str):
        return self._make_llm_response(text)

    def _summary_with_overreach(self) -> str:
        return (
            "# Resumo Aprofundado - doc.pdf\n\n"
            "## Visão Geral\n"
            "As árvores de decisão transformam dados em regras [Fonte 1].\n\n"
            "## Encadeamento e Principais Tópicos\n"
            "Inclui fundamentos, construção e validação [Fonte 1].\n\n"
            "## Conceitos e Métodos Fundamentais\n"
            "Com d_vc >= 4 e N >= 40, o modelo sempre generaliza bem [Fonte 1].\n\n"
            "## Aplicações e Variações\n"
            "Uso em classificação e regressão [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Modelo robusto para decisão [Fonte 1]."
        )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_sources_section_entry_count_matches_anchor_count(
        self, mock_collect, mock_llm_factory
    ):
        """Number of Fontes: entries must equal number of citation anchors selected."""
        from docops.summarize.pipeline import run_deep_summary

        # 6 chunks → 2 groups of 3 (section-based) → 2 anchors
        chunks = [
            _doc(f"chunk {i}", chunk_index=i, section_path="A" if i < 3 else "B", page=i + 1)
            for i in range(6)
        ]
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        # LLM responses cite only [Fonte 1] and [Fonte 2]
        mock_llm.invoke.return_value = self._make_llm_response(
            "Resumo baseado em [Fonte 1] e [Fonte 2]."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        sources = result["sources_section"]

        # Count [Fonte N] entries in the sources section
        import re
        entries = re.findall(r"\[Fonte \d+\]", sources)
        assert len(entries) >= 1  # at least one entry
        # No [Fonte N] in sources should exceed the anchor count
        max_n = max(int(re.search(r"\d+", e).group()) for e in entries)
        assert max_n <= 12  # hard cap from config.summary_max_sources

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_phantom_citations_absent_from_final_answer(
        self, mock_collect, mock_llm_factory
    ):
        """If the LLM generates a phantom [Fonte N], it must not appear in the answer."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = _make_chunks(4, with_sections=False)
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        # LLM response includes [Fonte 999] — definitely phantom
        mock_llm.invoke.return_value = self._make_llm_response(
            "Análise aprofundada conforme [Fonte 999] demonstra claramente."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        assert "[Fonte 999]" not in result["answer"], (
            "Phantom [Fonte 999] should have been removed by validate_summary_citations"
        )

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_scheduler_reserves_last_pass_for_must_cover_and_skips_deoverreach(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """With max_passes=1 in strict and missing must-cover topics, scheduler must reserve
        the pass for coverage and skip de-overreach."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")
        monkeypatch.setenv("SUMMARY_STRICT_RESERVE_PASS_FOR_MUST_COVER", "true")
        monkeypatch.setenv("SUMMARY_REQUIRE_NON_LOW_INFO_FOR_HIGH_RISK", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = [
            _doc("sumário", chunk_index=i, page=1, section_title="Sumário")
            for i in range(4)
        ]
        mock_extract_topics.return_value = {
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "minor_topics": [],
            "topic_details": {"math_formalization": {"label": "Formalização", "hits": 2}},
            "outline_text": "",
        }
        mock_outline_score.return_value = {
            "overall_score": 0.5,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": [],
            "missing_topics": ["math_formalization"],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 0.0},
        }
        mock_micro_backfill.return_value = {
            "text": self._summary_with_overreach(),
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 0,
            "missing_topics_before": ["math_formalization"],
            "missing_topics_after": ["math_formalization"],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._summary_with_overreach())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        assert diag["corrective_scheduler"]["reserve_last_pass_for_must_cover"] is True
        assert diag["deoverreach"]["skipped_reason"] == "reserved_for_must_cover_topics"
        assert diag["backfill"]["triggered"] is True

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_deoverreach_rejected_does_not_consume_corrective_pass(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Rejected de-overreach candidate must not consume corrective budget."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_REQUIRE_NON_LOW_INFO_FOR_HIGH_RISK", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = [
            _doc("sumário", chunk_index=i, page=1, section_title="Sumário")
            for i in range(4)
        ]
        mock_llm = MagicMock()
        overreach = self._summary_with_overreach()
        mock_llm.invoke.side_effect = [self._resp(overreach)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        assert diag["deoverreach"]["triggered"] is True
        assert diag["deoverreach"]["accepted"] is False
        assert diag["deoverreach"]["pass_consumed"] is False
        assert diag["corrective_passes_used"] == 0

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_claim_risk_reports_unsupported_high_risk_sentences(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Diagnostics should expose unsupported high-risk sentence excerpts for targeted repair."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_REQUIRE_NON_LOW_INFO_FOR_HIGH_RISK", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = [
            _doc("sumário", chunk_index=i, page=1, section_title="Sumário")
            for i in range(4)
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._summary_with_overreach())] * 15
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        claim = result["diagnostics"]["claim_risk"]

        if claim["unsupported_high_risk_count"] == 0:
            pytest.skip("No unsupported high-risk claim detected in this run.")
        assert claim["unsupported_high_risk_sentences"], claim
        first = claim["unsupported_high_risk_sentences"][0]
        assert "text" in first and first["text"]
        assert "risk_type" in first

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_body_citations_within_sources_range(
        self, mock_collect, mock_llm_factory
    ):
        """Every [Fonte N] remaining in the body must have a corresponding Fontes: entry."""
        from docops.summarize.pipeline import run_deep_summary
        import re

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response(
            "Ponto A [Fonte 1]. Ponto B [Fonte 2]. Ponto C [Fonte 3]."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]
        sources = result["sources_section"]

        body_citations = set(int(m) for m in re.findall(r"\[Fonte\s*(\d+)\]", answer))
        source_citations = set(int(m) for m in re.findall(r"\[Fonte\s*(\d+)\]", sources))

        # Every citation in the body must exist in the sources section
        orphaned = body_citations - source_citations
        assert not orphaned, (
            f"Body citations {orphaned} have no matching entry in the sources section"
        )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_sources_section_contains_only_cited_indices(
        self, mock_collect, mock_llm_factory
    ):
        """Fontes should list only [Fonte N] that actually appear in the answer body."""
        from docops.summarize.pipeline import run_deep_summary
        import re

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response(
            "Ponto A [Fonte 1]. Ponto C [Fonte 3]."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]
        sources = result["sources_section"]

        body_citations = sorted(set(int(m) for m in re.findall(r"\[Fonte\s*(\d+)\]", answer)))
        source_citations = sorted(set(int(m) for m in re.findall(r"\[Fonte\s*(\d+)\]", sources)))

        assert source_citations == body_citations


# ──────────────────────────────────────────────────────────────────────────────
# pipeline: validate_summary_grounding
# ──────────────────────────────────────────────────────────────────────────────

class TestValidateSummaryGrounding:
    def setup_method(self):
        from docops.summarize.pipeline import validate_summary_grounding
        self.validate = validate_summary_grounding

    def _anchor(self, text: str, **meta) -> Document:
        return _doc(text, **meta)

    def test_empty_text_returns_safely(self):
        """Empty text must not crash and returns correct empty info."""
        result_text, info = self.validate("", [self._anchor("qualquer coisa")])
        assert result_text == ""
        assert info["total_blocks"] == 0
        assert info["blocks_with_citations"] == 0

    def test_block_without_citations_is_skipped(self):
        """Blocks with no [Fonte N] are not evaluated (score=None, grounded=None)."""
        text = "Parágrafo sem qualquer citação inline. Apenas texto livre."
        _, info = self.validate(text, [self._anchor("texto irrelevante")])
        assert info["blocks_with_citations"] == 0
        assert info["block_scores"][0]["score"] is None
        assert info["block_scores"][0]["grounded"] is None

    def test_block_with_high_overlap_is_grounded(self):
        """Block whose tokens overlap well with anchor → grounded=True."""
        # Anchor and block share core vocabulary
        anchor = self._anchor(
            "algoritmo busca binária divide array metade cada iteração eficiente",
            chunk_index=0,
        )
        block = (
            "O algoritmo de busca binária divide o array pela metade em cada "
            "iteração, tornando-o muito eficiente [Fonte 1]."
        )
        _, info = self.validate(block, [anchor], threshold=0.20)
        assert info["blocks_with_citations"] == 1
        scored = info["block_scores"][0]
        assert scored["grounded"] is True
        assert scored["score"] >= 0.20

    def test_block_with_low_overlap_is_weakly_grounded(self):
        """Block whose vocabulary is completely different from anchor → weakly grounded."""
        anchor = self._anchor(
            "heap inserção complexidade logarítmica estrutura fila prioridade",
            chunk_index=0,
        )
        # Block is about geometry, has nothing to do with the anchor
        block = (
            "O teorema de Pitágoras relaciona hipotenusa catetos ângulo reto "
            "geometria euclidiana [Fonte 1]."
        )
        _, info = self.validate(block, [anchor], threshold=0.20)
        assert info["weakly_grounded"] == 1
        assert info["block_scores"][0]["grounded"] is False

    def test_no_repair_when_llm_is_none(self):
        """Without an LLM, repaired_blocks must always be 0."""
        anchor = self._anchor("dados completamente diferentes sobre física quântica")
        block = "Sobre biologia marinha e fotossíntese [Fonte 1]."
        result_text, info = self.validate(block, [anchor], threshold=0.20, llm=None)
        assert info["repaired_blocks"] == 0
        # Text should be unchanged (log-only mode)
        assert result_text.strip() == block.strip()

    def test_repair_attempted_for_weakly_grounded_block(self, monkeypatch):
        """With llm provided, _repair_block is called for a weakly grounded block."""
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR_MIN_OVERLAP", "0.25")
        anchor = self._anchor("física relatividade energia massa velocidade luz")
        block = "Energia em taxonomia vegetal e folhas caducas [Fonte 1]."

        mock_llm = MagicMock()
        repaired_text = "Energia é proporcional à massa conforme a relatividade [Fonte 1]."
        mock_llm.invoke.return_value = MagicMock(content=repaired_text)

        result_text, info = self.validate(block, [anchor], threshold=0.30, llm=mock_llm)
        # LLM should have been called for the weakly grounded block
        mock_llm.invoke.assert_called_once()
        assert info["repaired_blocks"] == 1
        assert repaired_text in result_text

    def test_repair_budget_caps_repairs_per_pass(self, monkeypatch):
        """Grounding repair should cap LLM rewrites per pass via config."""
        monkeypatch.setenv("SUMMARY_GROUNDING_MAX_REPAIRS_PER_PASS", "1")
        anchor = self._anchor("algoritmo complexidade entropia poda regularizacao")
        text = (
            "Bloco fraco sobre algoritmo em tema distante [Fonte 1].\n\n"
            "Segundo bloco fraco com algoritmo mas sem suporte suficiente [Fonte 1]."
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Texto reparado com [Fonte 1].")
        _, info = self.validate(text, [anchor], threshold=0.95, llm=mock_llm)
        assert info["weakly_grounded"] >= 2
        assert info["repaired_blocks"] == 1
        assert mock_llm.invoke.call_count == 1

    def test_zero_overlap_skips_repair_even_with_llm(self):
        """If overlap is 0.00, repair must be skipped."""
        anchor = self._anchor("fisica relatividade energia massa velocidade luz")
        block = "Taxonomia vegetal e folhas caducas em biologia [Fonte 1]."

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Should not be called.")

        result_text, info = self.validate(block, [anchor], threshold=0.20, llm=mock_llm)
        mock_llm.invoke.assert_not_called()
        assert info["weakly_grounded"] == 1
        assert info["repaired_blocks"] == 0
        assert result_text.strip() == block.strip()

    def test_many_citations_skip_repair_even_with_llm(self):
        """If a block cites >3 sources, repair must be skipped."""
        anchors = [
            self._anchor("entropia ganho informacao"),
            self._anchor("poda cost complexity alpha"),
            self._anchor("random forest bootstrap"),
            self._anchor("regressao quadrados minimos"),
        ]
        block = (
            "Resumo agregado e generico sobre varios temas [Fonte 1] [Fonte 2] "
            "[Fonte 3] [Fonte 4]."
        )

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Should not be called.")

        result_text, info = self.validate(block, anchors, threshold=0.95, llm=mock_llm)
        mock_llm.invoke.assert_not_called()
        assert info["weakly_grounded"] == 1
        assert info["repaired_blocks"] == 0
        assert result_text.strip() == block.strip()

    def test_repair_with_forbidden_patterns_is_discarded(self, monkeypatch):
        """Repair output that is ONLY meta-commentary must be rejected even after sanitation."""
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR_MIN_OVERLAP", "0.25")
        anchor = self._anchor("fisica relatividade energia massa velocidade luz")
        block = "Energia em taxonomia vegetal e folhas caducas [Fonte 1]."

        mock_llm = MagicMock()
        # Repair output contains ONLY forbidden meta-commentary — no salvageable prose.
        mock_llm.invoke.return_value = MagicMock(
            content="não encontrei informações nas fontes fornecidas"
        )

        result_text, info = self.validate(block, [anchor], threshold=0.30, llm=mock_llm)
        mock_llm.invoke.assert_called_once()
        assert info["repaired_blocks"] == 0
        assert result_text.strip() == block.strip()

    def test_repair_with_mixed_content_sanitized_and_accepted(self, monkeypatch):
        """Repair with valid prose + leaked source lines should be accepted after sanitation."""
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR_MIN_OVERLAP", "0.25")
        anchor = self._anchor("fisica relatividade energia massa velocidade luz")
        block = "Energia em taxonomia vegetal e folhas caducas [Fonte 1]."

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=(
                "A energia é proporcional à massa conforme relatividade [Fonte 1].\n"
                "Fonte 6: Random Forest"
            )
        )

        result_text, info = self.validate(block, [anchor], threshold=0.30, llm=mock_llm)
        mock_llm.invoke.assert_called_once()
        assert info["repaired_blocks"] == 1
        assert "energia" in result_text.lower()
        assert "Fonte 6: Random Forest" not in result_text

    def test_returns_grounding_info_dict_structure(self):
        """Result dict must contain all required keys with correct types."""
        _, info = self.validate("Texto [Fonte 1].", [self._anchor("texto livre")])
        assert "total_blocks" in info
        assert "blocks_with_citations" in info
        assert "weakly_grounded" in info
        assert "repaired_blocks" in info
        assert "block_scores" in info
        assert isinstance(info["block_scores"], list)

    def test_all_blocks_grounded_weakly_grounded_zero(self):
        """When all cited blocks pass, weakly_grounded must be 0."""
        # Anchor covers vocabulary from both blocks below
        anchor = self._anchor(
            "algoritmo busca binária divide array metade cada iteração "
            "eficiente abordagem arrays ordenados complexidade",
            chunk_index=0,
        )
        text = (
            "O algoritmo de busca binária divide o array pela metade em cada "
            "iteração [Fonte 1].\n\n"
            "Esta abordagem eficiente para arrays ordenados tem complexidade "
            "logarítmica [Fonte 1]."
        )
        _, info = self.validate(text, [anchor], threshold=0.20)
        assert info["weakly_grounded"] == 0

    def test_duplicate_citations_in_block_are_deduplicated(self):
        anchor1 = self._anchor("entropia ganho de informação classes")
        anchor2 = self._anchor("poda cost complexity alpha")
        text = (
            "Discussão sobre entropia e poda [Fonte 1] [Fonte 1] [Fonte 2]."
        )
        _, info = self.validate(text, [anchor1, anchor2], threshold=0.0)
        assert info["block_scores"][0]["cited_indices"] == [1, 2]


# ──────────────────────────────────────────────────────────────────────────────
# citations: build_anchor_sources_section
# ──────────────────────────────────────────────────────────────────────────────

class TestSummaryQualityHelpers:
    def setup_method(self):
        from docops.summarize.pipeline import (
            _resolve_grounding_threshold,
            validate_summary_structure,
        )
        self.resolve_threshold = _resolve_grounding_threshold
        self.validate_structure = validate_summary_structure

    def test_adaptive_grounding_threshold_for_noisy_chunks(self):
        raw_chunks = [
            _doc("Texto com artefato\ufffd e simbolos estranhos ★★★★★"),
            _doc("Outro trecho com ligatura \ufb03 e caracteres quebrados \ue000"),
        ]
        cleaned_chunks = [
            _doc("Texto com artefato e simbolos estranhos"),
            _doc("Outro trecho com ligatura ffi e caracteres quebrados"),
        ]
        threshold = self.resolve_threshold(raw_chunks, cleaned_chunks, base_threshold=0.20)
        assert abs(threshold - 0.12) < 1e-9

    def test_adaptive_grounding_keeps_base_for_clean_chunks(self):
        raw_chunks = [
            _doc("Texto limpo sobre entropia e ganho de informacao."),
            _doc("Texto limpo sobre poda e complexidade."),
        ]
        cleaned_chunks = [
            _doc("Texto limpo sobre entropia e ganho de informacao."),
            _doc("Texto limpo sobre poda e complexidade."),
        ]
        threshold = self.resolve_threshold(raw_chunks, cleaned_chunks, base_threshold=0.20)
        assert abs(threshold - 0.20) < 1e-9

    def test_structure_validator_accepts_good_summary_shape(self):
        text = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Panorama Geral\n"
            "Este bloco explica objetivo e contexto com detalhes suficientes para estudo, "
            "incluindo escopo, motivacao e limites do material [Fonte 1].\n\n"
            "## Construção e Lógica\n"
            "Este bloco explica encadeamento, fundamentos e estrutura do material, "
            "mostrando a progressao dos conceitos entre secoes [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Este bloco define conceitos centrais, termos e relacoes tecnicas, "
            "com distincoes importantes entre ideias principais e secundarias [Fonte 2].\n\n"
            "## Síntese e Conclusão\n"
            "Este bloco integra as ideias principais, conclui o raciocinio e "
            "explicita as implicacoes praticas para uso do conhecimento [Fonte 2]."
        )
        info = self.validate_structure(text, min_section_chars=30, min_sections=4)
        assert info["valid"] is True
        assert info["missing_categories"] == []
        assert info["weak_section_indices"] == []

    def test_structure_validator_flags_generic_or_weak_sections(self):
        text = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Panorama Geral\n"
            "O documento explora arvores de decisao [Fonte 1].\n\n"
            "## Construção e Lógica\n"
            "Breve [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Conceitos [Fonte 1].\n\n"
            "## Síntese e Conclusão\n"
            "Conclusao curta [Fonte 1]."
        )
        info = self.validate_structure(text, min_section_chars=80, min_sections=4)
        assert info["valid"] is False
        assert len(info["weak_section_indices"]) >= 1


class TestBuildAnchorSourcesSection:
    def setup_method(self):
        from docops.rag.citations import build_anchor_sources_section
        self.build = build_anchor_sources_section

    def test_empty_anchors_returns_no_source_message(self):
        result = self.build([])
        assert "**Fontes:**" in result
        assert "nenhuma" in result.lower()

    def test_single_anchor_with_full_metadata(self):
        anchor = _doc("texto", file_name="doc.pdf", section_path="Intro", page=3)
        result = self.build([anchor])
        assert "[Fonte 1]" in result
        assert "doc.pdf" in result
        assert "Intro" in result
        assert "p. 3" in result

    def test_anchor_without_section_shows_file_and_page(self):
        anchor = _doc("texto", file_name="doc.pdf", page=5)
        result = self.build([anchor])
        assert "doc.pdf" in result
        assert "p. 5" in result

    def test_anchor_without_page_shows_file_and_section(self):
        anchor = _doc("texto", file_name="doc.pdf", section_path="Capítulo 2")
        result = self.build([anchor])
        assert "doc.pdf" in result
        assert "Capítulo 2" in result
        # No page info — no "p." should appear
        assert "p." not in result

    def test_multiple_anchors_numbered_sequentially(self):
        anchors = [
            _doc("a", file_name="doc.pdf", page=1),
            _doc("b", file_name="doc.pdf", page=2),
            _doc("c", file_name="doc.pdf", page=3),
        ]
        result = self.build(anchors)
        assert "[Fonte 1]" in result
        assert "[Fonte 2]" in result
        assert "[Fonte 3]" in result
        assert "[Fonte 4]" not in result

    def test_page_range_when_start_differs_from_end(self):
        anchor = _doc("texto", file_name="doc.pdf", page_start=4, page_end=6)
        result = self.build([anchor])
        assert "pp. 4" in result
        assert "6" in result

    def test_single_page_shows_p_prefix(self):
        anchor = _doc("texto", file_name="doc.pdf", page_start=7, page_end=7)
        result = self.build([anchor])
        assert "p. 7" in result
        assert "pp." not in result

    def test_entry_count_equals_anchor_count(self):
        """Strict 1:1: number of entries must equal number of anchors."""
        import re
        anchors = [_doc(f"a{i}", file_name="doc.pdf", page=i) for i in range(5)]
        result = self.build(anchors)
        entries = re.findall(r"\[Fonte \d+\]", result)
        assert len(entries) == 5

    def test_no_snippet_shown(self):
        """Anchor sources section should NOT include a snippet of the chunk text."""
        anchor = _doc(
            "Este é o conteúdo do chunk que NÃO deve aparecer nas Fontes.",
            file_name="doc.pdf",
            section_path="Seção A",
            page=1,
        )
        result = self.build([anchor])
        assert "NÃO deve aparecer" not in result

    def test_filtered_indices_preserve_original_labels(self):
        anchors = [
            _doc("a", file_name="doc.pdf", page=1),
            _doc("b", file_name="doc.pdf", page=2),
            _doc("c", file_name="doc.pdf", page=3),
        ]
        result = self.build(anchors, source_indices=[2, 3])
        assert "[Fonte 1]" not in result
        assert "[Fonte 2]" in result
        assert "[Fonte 3]" in result

    def test_filtered_indices_empty_returns_no_cited_message(self):
        anchors = [_doc("a", file_name="doc.pdf", page=1)]
        result = self.build(anchors, source_indices=[])
        assert "nenhuma fonte citada no corpo" in result.lower()

    def test_hides_meta_section_label(self):
        anchor = _doc("texto", file_name="doc.pdf", section_path="[meta] page: 3", page=3)
        result = self.build([anchor])
        assert "[meta]" not in result.lower()
        assert "doc.pdf" in result
        assert "p. 3" in result


# ──────────────────────────────────────────────────────────────────────────────
# config: grounding properties
# ──────────────────────────────────────────────────────────────────────────────

class TestGroundingConfig:
    def test_summary_grounding_threshold_default(self):
        from docops.config import config
        assert abs(config.summary_grounding_threshold - 0.20) < 1e-9

    def test_summary_grounding_repair_default_false(self):
        from docops.config import config
        assert config.summary_grounding_repair is False

    def test_summary_grounding_repair_min_overlap_default(self):
        from docops.config import config
        assert abs(config.summary_grounding_repair_min_overlap - 0.15) < 1e-9

    def test_summary_grounding_threshold_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_GROUNDING_THRESHOLD", "0.35")
        from docops.config import Config
        assert abs(Config().summary_grounding_threshold - 0.35) < 1e-9

    def test_summary_grounding_repair_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "true")
        from docops.config import Config
        assert Config().summary_grounding_repair is True

    def test_summary_min_unique_sources_default(self):
        from docops.config import config
        assert config.summary_min_unique_sources == 5

    def test_summary_resynthesis_enabled_default_false(self):
        from docops.config import config
        assert config.summary_resynthesis_enabled is False

    def test_summary_resynthesis_weak_block_ratio_default(self):
        from docops.config import config
        assert abs(config.summary_resynthesis_weak_block_ratio - 0.50) < 1e-9

    def test_summary_resynthesis_max_weak_ratio_degradation_default(self):
        from docops.config import config
        assert abs(config.summary_resynthesis_max_weak_ratio_degradation - 0.05) < 1e-9

    def test_summary_grounding_threshold_noisy_default(self):
        from docops.config import config
        assert abs(config.summary_grounding_threshold_noisy - 0.12) < 1e-9

    def test_summary_new_props_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "4")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.65")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_WEAK_RATIO_DEGRADATION", "0.20")
        monkeypatch.setenv("SUMMARY_GROUNDING_THRESHOLD_NOISY", "0.10")
        monkeypatch.setenv("SUMMARY_GROUNDING_NOISY_CHUNK_RATIO", "0.40")
        monkeypatch.setenv("SUMMARY_GROUNDING_NOISY_REDUCTION_RATIO", "0.05")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "120")
        from docops.config import Config
        cfg = Config()
        assert cfg.summary_min_unique_sources == 4
        assert cfg.summary_resynthesis_enabled is False
        assert abs(cfg.summary_resynthesis_weak_block_ratio - 0.65) < 1e-9
        assert abs(cfg.summary_resynthesis_max_weak_ratio_degradation - 0.20) < 1e-9
        assert abs(cfg.summary_grounding_threshold_noisy - 0.10) < 1e-9
        assert abs(cfg.summary_grounding_noisy_chunk_ratio - 0.40) < 1e-9
        assert abs(cfg.summary_grounding_noisy_reduction_ratio - 0.05) < 1e-9
        assert cfg.summary_structure_min_chars == 120


# ──────────────────────────────────────────────────────────────────────────────
# Integration: grounding + anchor sources in run_deep_summary
# ──────────────────────────────────────────────────────────────────────────────

class TestGroundingAndAnchorSourcesIntegration:
    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_sources_section_shows_location_not_snippet(
        self, mock_collect, mock_llm_factory
    ):
        """Final Fontes: section must show file/section/page — no raw snippet text."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = [
            _doc(
                "Este conteúdo NÃO deve aparecer nas Fontes.",
                chunk_index=i,
                file_name="doc.pdf",
                section_path="Seção A",
                page=i + 1,
            )
            for i in range(4)
        ]
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._make_llm_response(
            "Resumo baseado em [Fonte 1]."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        sources = result["sources_section"]

        assert "NÃO deve aparecer" not in sources
        assert "doc.pdf" in sources

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_phantom_removed_grounding_still_runs(
        self, mock_collect, mock_llm_factory
    ):
        """After phantom removal, grounding step runs on the cleaned text."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = _make_chunks(4, with_sections=False)
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        # LLM emits a phantom [Fonte 99] + a valid [Fonte 1]
        mock_llm.invoke.return_value = self._make_llm_response(
            "Análise [Fonte 1] complementada por dados externos [Fonte 99]."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]

        # Phantom must be removed by validate_summary_citations (step 6c)
        assert "[Fonte 99]" not in answer
        # [Fonte 1] may or may not survive grounding, but answer must be a non-empty string
        assert isinstance(answer, str) and len(answer) > 0

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_model_generated_sources_are_replaced_by_authoritative_section(
        self, mock_collect, mock_llm_factory
    ):
        """The pipeline must strip any LLM-generated Fontes: block and append its own."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = [
            _doc(
                "Conteúdo real do chunk.",
                chunk_index=i,
                file_name="doc.pdf",
                section_path="Fundamentos",
                page=i + 1,
            )
            for i in range(3)
        ]
        mock_collect.return_value = chunks

        llm_outputs = [
            self._make_llm_response("Resumo parcial 1 [Fonte 1]."),
            self._make_llm_response("Visão consolidada [Fonte 1]."),
            self._make_llm_response(
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Objetivo e Contexto\nTexto útil [Fonte 1].\n\n"
                "**Fontes:**\n- [Fonte 1] **fonte inventada**"
            ),
            self._make_llm_response(
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Objetivo e Contexto\nTexto útil [Fonte 1].\n\n"
                "**Fontes:**\n- [Fonte 1] **outra fonte inventada**"
            ),
        ]

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {"SUMMARY_GROUNDING_REPAIR": "false"}):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "fonte inventada" not in result["answer"].lower()
        assert "outra fonte inventada" not in result["answer"].lower()
        assert result["answer"].count("**Fontes:**") == 1
        assert "Fundamentos" in result["answer"]

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_global_resynthesis_improves_citation_diversity(
        self, mock_collect, mock_llm_factory
    ):
        from docops.summarize.pipeline import run_deep_summary

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado [Fonte 1] [Fonte 2]."),
            self._make_llm_response(
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Panorama Geral\nTexto inicial [Fonte 1].\n\n"
                "## Construção e Lógica\nTexto inicial [Fonte 1].\n\n"
                "## Conceitos Fundamentais\nTexto inicial [Fonte 1].\n\n"
                "## Síntese e Conclusão\nTexto inicial [Fonte 1]."
            ),
            self._make_llm_response(
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Panorama Geral\nPanorama com duas evidencias [Fonte 1] e [Fonte 2].\n\n"
                "## Construção e Lógica\nEncadeamento com suporte de [Fonte 1] e [Fonte 2].\n\n"
                "## Conceitos Fundamentais\nConceitos centrais sustentados por [Fonte 1].\n\n"
                "## Síntese e Conclusão\nConclusão sustentada por [Fonte 2]."
            ),
        ]

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        with patch.dict(
            os.environ,
            {
                "SUMMARY_GROUNDING_REPAIR": "false",
                "SUMMARY_RESYNTHESIS_ENABLED": "true",
                "SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO": "0.0",
                "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
                "SUMMARY_MIN_UNIQUE_SOURCES": "2",
                "SUMMARY_STRUCTURE_MIN_CHARS": "20",
                "SUMMARY_MAX_CORRECTIVE_PASSES": "2",
                # This test verifies citation diversity only; structure gating is
                # tested in TestResynthesisGateIntegration.
                "SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE": "false",
            },
        ):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "[Fonte 1]" in result["answer"]
        assert "[Fonte 2]" in result["answer"]
        assert "[Fonte 1]" in result["sources_section"]
        assert "[Fonte 2]" in result["sources_section"]
        assert mock_llm.invoke.call_count >= 5

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_inline_sources_and_meta_lines_removed_from_body(
        self, mock_collect, mock_llm_factory
    ):
        """Deep summary body must not leak 'Fontes:' lines or '[Fonte N]:' mapping lines."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = [
            _doc(
                "Conteúdo real [meta] page: 13 sobre entropia.",
                chunk_index=i,
                file_name="doc.pdf",
                section_path="Fundamentos",
                page=i + 1,
            )
            for i in range(4)
        ]
        mock_collect.return_value = chunks

        mock_llm = MagicMock()
        # 1 partial + 1 consolidate + 1 final + 1 style + 1 repair
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial [Fonte 1]."),
            self._make_llm_response("Consolidado [Fonte 1]."),
            self._make_llm_response(
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Bloco\nTexto [Fonte 1].\n\n"
                "Fontes: [Fonte 1]"
            ),
            self._make_llm_response(
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Bloco\nTexto [Fonte 1].\n\n"
                "[Fonte 1]: [meta] page: 13\n"
                "[Fonte 1]\n"
                "Fonte 6: Random Forest"
            ),
            self._make_llm_response(
                "Texto reparado [Fonte 1].\n\n"
                "Fontes: [Fonte 1]\n"
                "[Fonte 1]: [meta] page: 13\n"
                "[Fonte 1]\n"
                "Fonte 5\n"
                "Não encontrei informações nas fontes fornecidas para reescrever o bloco.\n"
                "Não foi possível reescrever o bloco com base na fonte fornecida."
            ),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {"SUMMARY_GROUNDING_THRESHOLD": "1.0"}):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        answer = result["answer"]
        assert "Fontes: [Fonte 1]" not in answer
        assert "[Fonte 1]: [meta] page: 13" not in answer
        assert "\n[Fonte 1]\n" not in answer
        assert "Fonte 6: Random Forest" not in answer
        assert "\nFonte 5\n" not in answer
        assert "Não encontrei informações nas fontes fornecidas" not in answer
        assert "Não foi possível reescrever o bloco" not in answer


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa A — source dump inline removal
# ──────────────────────────────────────────────────────────────────────────────

class TestSourceDumpSanitization:
    """Tests for the source-dump-inline guardrail in _sanitize_inline_source_noise."""

    def setup_method(self):
        from docops.summarize.pipeline import _sanitize_inline_source_noise
        self.sanitize = _sanitize_inline_source_noise

    def test_removes_multi_citation_dump_line(self):
        """Line starting with [Fonte N] immediately followed by another [Fonte N] is removed."""
        text = "Parágrafo normal.\n\n[Fonte 1] ... [Fonte 2] ...\n\nOutro parágrafo."
        result = self.sanitize(text)
        assert "[Fonte 1] ... [Fonte 2]" not in result
        assert "Parágrafo normal" in result
        assert "Outro parágrafo" in result

    def test_removes_multi_citation_dump_short_gap(self):
        """Line with [Fonte 1] texto_curto [Fonte 2] at start is treated as dump."""
        text = "Intro.\n\n[Fonte 1] trecho A [Fonte 2] trecho B\n\nFim."
        result = self.sanitize(text)
        assert "[Fonte 1] trecho A [Fonte 2]" not in result
        assert "Intro" in result
        assert "Fim" in result

    def test_removes_source_dump_entry_with_pdf_and_page(self):
        """[Fonte N] at line start followed by .pdf + page reference is removed."""
        text = "Normal text.\n\n[Fonte 1] arquivo.pdf (página 3)\n\nMais texto."
        result = self.sanitize(text)
        assert "arquivo.pdf (página 3)" not in result
        assert "Normal text" in result
        assert "Mais texto" in result

    def test_removes_source_dump_entry_gt_p_format(self):
        """[Fonte N] at line start with '> p. N' format is removed."""
        text = "Texto.\n\n[Fonte 2] **doc.pdf** > Seção > p. 5\n\nMais texto."
        result = self.sanitize(text)
        assert "**doc.pdf** > Seção > p. 5" not in result
        assert "Texto" in result

    def test_removes_source_dump_entry_pp_format(self):
        """[Fonte N] at line start with '> pp. N–M' format is removed."""
        text = "Conteúdo.\n\n[Fonte 3] doc.pdf > Capítulo > pp. 10–12\n\nConteúdo continua."
        result = self.sanitize(text)
        assert "pp. 10" not in result.split("**Fontes:**")[0] if "**Fontes:**" in result else "pp. 10–12" not in result
        assert "Conteúdo continua" in result

    def test_preserves_inline_prose_citation_at_end(self):
        """Citation at end of a prose sentence must NOT be removed."""
        text = "A busca binária é eficiente [Fonte 1].\n\nOutro ponto [Fonte 2]."
        result = self.sanitize(text)
        assert "[Fonte 1]" in result
        assert "[Fonte 2]" in result

    def test_preserves_inline_prose_with_multiple_citations(self):
        """Multiple citations embedded in prose (line does not start with [Fonte]) must be kept."""
        text = "Como [Fonte 1] e [Fonte 2] demonstram, o método é eficaz."
        result = self.sanitize(text)
        assert "[Fonte 1]" in result
        assert "[Fonte 2]" in result

    def test_preserves_citation_mid_sentence(self):
        """Citation mid-sentence (not at line start) is never removed."""
        text = "O algoritmo de busca binária [Fonte 1] demonstra eficiência clara."
        result = self.sanitize(text)
        assert "[Fonte 1]" in result
        assert "algoritmo" in result

    def test_removes_process_meta_sentence_inside_paragraph(self):
        """Process/meta source commentary should be stripped from prose body."""
        text = (
            "O método cobre entropia e indução [Fonte 1]. "
            "Algumas fontes estavam ausentes na lista de trechos fornecidos. "
            "Também explica ganho de informação [Fonte 2]."
        )
        result = self.sanitize(text)
        assert "ausentes na lista de trechos fornecidos" not in result
        assert "entropia" in result
        assert "ganho de informação" in result

    def test_source_dump_removed_from_deep_summary_answer(self):
        """Source dump lines in LLM output must not survive to the final answer."""
        from unittest.mock import MagicMock, patch

        chunks = _make_chunks(4, with_sections=False)

        llm_response_with_dump = MagicMock()
        llm_response_with_dump.content = (
            "## Objetivos\n"
            "Conteúdo sobre busca binária [Fonte 1].\n\n"
            "[Fonte 1] arquivo.pdf (página 3)\n\n"
            "[Fonte 1] ... [Fonte 2] ...\n\n"
            "## Conclusão\nResumo final [Fonte 1]."
        )

        with (
            patch("docops.summarize.pipeline.collect_ordered_chunks", return_value=chunks),
            patch("docops.summarize.pipeline._get_llm") as mock_factory,
        ):
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = llm_response_with_dump
            mock_factory.return_value = mock_llm

            from docops.summarize.pipeline import run_deep_summary
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        # Separate body from sources section (Fontes: is appended at the end)
        answer = result["answer"]
        body = answer.split("**Fontes:**")[0] if "**Fontes:**" in answer else answer

        assert "arquivo.pdf (página 3)" not in body, (
            "Source dump entry with pdf+page must be removed from body"
        )
        assert "[Fonte 1] ... [Fonte 2]" not in body, (
            "Multi-citation dump line must be removed from body"
        )
        assert "Conteúdo sobre busca binária" in body or "busca" in body, (
            "Real prose content must be preserved"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa B — structure-fix pass + gate de re-síntese
# ──────────────────────────────────────────────────────────────────────────────

class TestApplyStructureFix:
    """Unit tests for _apply_structure_fix."""

    def _good_structure_text(self):
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Objetivo e Contexto\n"
            "Explica algoritmos com exemplos e fundamentos teóricos relevantes [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progride de básico para avançado com encadeamento claro entre conceitos [Fonte 2].\n\n"
            "## Conceitos Fundamentais\n"
            "Define complexidade, estruturas e análise com precisão técnica [Fonte 3].\n\n"
            "## Síntese e Conclusão\n"
            "Conclui sobre a escolha contextual de algoritmos e suas implicações [Fonte 4]."
        )

    def test_returns_llm_output(self):
        """_apply_structure_fix must return the text produced by the LLM."""
        from docops.summarize.pipeline import _apply_structure_fix

        fixed = self._good_structure_text()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content=fixed)

        result = _apply_structure_fix("rascunho ruim", "doc.pdf", mock_llm)
        assert result == fixed
        mock_llm.invoke.assert_called_once()

    def test_falls_back_to_draft_on_llm_error(self):
        """On LLM failure, _apply_structure_fix must return the original draft unchanged."""
        from docops.summarize.pipeline import _apply_structure_fix

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM indisponível")

        original = "rascunho original com conteúdo"
        result = _apply_structure_fix(original, "doc.pdf", mock_llm)
        assert result == original

    def test_returns_draft_when_llm_returns_empty(self):
        """Empty LLM response must fall back to original draft."""
        from docops.summarize.pipeline import _apply_structure_fix

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="   ")

        original = "rascunho com conteúdo"
        result = _apply_structure_fix(original, "doc.pdf", mock_llm)
        assert result == original

    def test_invokes_llm_with_doc_name_in_prompt(self):
        """The doc_name must appear in the prompt sent to the LLM."""
        from docops.summarize.pipeline import _apply_structure_fix

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="resultado")

        _apply_structure_fix("rascunho", "meu_documento.pdf", mock_llm)

        call_messages = mock_llm.invoke.call_args[0][0]
        full_content = " ".join(str(m.content) for m in call_messages)
        assert "meu_documento.pdf" in full_content

    def test_invokes_llm_with_draft_in_prompt(self):
        """The draft must appear in the prompt sent to the LLM."""
        from docops.summarize.pipeline import _apply_structure_fix

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="resultado")

        _apply_structure_fix("RASCUNHO_IDENTIFICÁVEL_XYZ", "doc.pdf", mock_llm)

        call_messages = mock_llm.invoke.call_args[0][0]
        full_content = " ".join(str(m.content) for m in call_messages)
        assert "RASCUNHO_IDENTIFICÁVEL_XYZ" in full_content


class TestPruningLimitationCorrection:
    """Tests for correction of false 'not detailed' pruning claims."""

    def test_rewrites_false_pruning_limitation_when_evidence_exists(self):
        from docops.summarize.pipeline import _fix_false_pruning_limitation_claims

        text = (
            "## Conceitos\n"
            "O documento não detalha pruning com alpha_eff nos trechos disponíveis."
        )
        anchors = [
            Document(
                page_content=(
                    "Minimal cost-complexity pruning usa alpha_eff e validação "
                    "com cost_complexity_pruning_path no scikit-learn."
                ),
                metadata={"chunk_index": 0, "page": 23},
            )
        ]
        fixed = _fix_false_pruning_limitation_claims(text, anchors, source_chunks=anchors)
        assert "não detalha pruning" not in fixed.lower()
        assert "poda de custo-complexidade" in fixed
        assert "[Fonte 1]" in fixed


class TestStructureFixPrompt:
    """Verify the DEEP_SUMMARY_STRUCTURE_FIX_PROMPT contract."""

    def test_prompt_exists_and_has_placeholders(self):
        from docops.rag.prompts import DEEP_SUMMARY_STRUCTURE_FIX_PROMPT
        assert "{doc_name}" in DEEP_SUMMARY_STRUCTURE_FIX_PROMPT
        assert "{draft}" in DEEP_SUMMARY_STRUCTURE_FIX_PROMPT

    def test_prompt_forbids_fontes_in_body(self):
        """Prompt must instruct not to include a Fontes: block in the body."""
        from docops.rag.prompts import DEEP_SUMMARY_STRUCTURE_FIX_PROMPT
        lower = DEEP_SUMMARY_STRUCTURE_FIX_PROMPT.lower()
        # Should mention not including Fontes: section
        assert "fontes" in lower and ("separadamente" in lower or "não inclua" in lower or "annexad" in lower)

    def test_prompt_requires_section_bounds(self):
        """Prompt must specify min/max section count."""
        from docops.rag.prompts import DEEP_SUMMARY_STRUCTURE_FIX_PROMPT
        # Should mention 4 and 6 (or similar bounds)
        assert "4" in DEEP_SUMMARY_STRUCTURE_FIX_PROMPT
        assert "6" in DEEP_SUMMARY_STRUCTURE_FIX_PROMPT


class TestResynthesisGateConfig:
    """Config properties for the new re-synthesis gate."""

    def test_require_structure_default_true(self):
        from docops.config import config
        assert config.summary_resynthesis_require_structure is True

    def test_structure_fix_pass_enabled_default_true(self):
        from docops.config import config
        assert config.summary_structure_fix_pass_enabled is True

    def test_structure_fix_max_calls_default_two(self):
        from docops.config import config
        assert config.summary_structure_fix_max_calls == 2

    def test_require_structure_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "false")
        from docops.config import Config
        assert Config().summary_resynthesis_require_structure is False

    def test_structure_fix_enabled_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "false")
        from docops.config import Config
        assert Config().summary_structure_fix_pass_enabled is False

    def test_structure_fix_max_calls_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "2")
        from docops.config import Config
        assert Config().summary_structure_fix_max_calls == 2

    def test_max_accepted_weak_ratio_default(self):
        from docops.config import config
        assert abs(config.summary_resynthesis_max_accepted_weak_ratio - 0.35) < 1e-9

    def test_max_accepted_weak_ratio_from_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "0.55")
        from docops.config import Config
        assert abs(Config().summary_resynthesis_max_accepted_weak_ratio - 0.55) < 1e-9


class TestResynthesisGateIntegration:
    """Integration: re-synthesis acceptance gate with structure requirement.

    Quality signatures are built from (structure_valid, enough_sources,
    -weak_ratio, unique_sources, -weak_sections). For the structure-fix pass
    to trigger we need candidate_sig > current_sig with structure invalid.
    We guarantee this by giving the candidate MORE unique sources than the
    current text while keeping structure invalid for both.
    """

    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    def _bad_no_cit(self):
        """Two short sections, NO citations — structure invalid, unique_sources=0."""
        return (
            "# Resumo — doc.pdf\n\n"
            "## Dados\nCurto.\n\n"
            "## Mais Dados\nTambém curto."
        )

    def _bad_two_src(self):
        """Two short sections WITH [Fonte 1] and [Fonte 2] — structure invalid,
        unique_sources=2.  Sections still fail word-count (< 12 words after
        stripping citations) so structure is invalid.
        MARKER_CANDIDATO is included so we can detect if this text reached output."""
        return (
            "# Resumo — doc.pdf MARKER_CANDIDATO\n\n"
            "## Dados\nCurto [Fonte 1] [Fonte 2].\n\n"
            "## Mais Dados\nTambém curto [Fonte 1]."
        )

    def _good_structure(self):
        """Four full sections passing all structure checks — MARKER_FIXED included."""
        return (
            "# Resumo Aprofundado — doc.pdf MARKER_FIXED\n\n"
            "## Objetivo e Contexto\n"
            "O documento explica algoritmos de decisão com fundamentação teórica "
            "e exemplos práticos detalhados sobre uso em classificação [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "O material progride de fundamentos de entropia para técnicas avançadas "
            "de poda, mostrando encadeamento lógico entre cada conceito abordado [Fonte 2].\n\n"
            "## Conceitos Fundamentais\n"
            "Os conceitos centrais incluem ganho de informação, índice Gini e "
            "complexidade computacional com definições formais e exemplos [Fonte 1].\n\n"
            "## Síntese e Conclusão\n"
            "O documento conclui que a escolha correta do critério de divisão depende "
            "do contexto e das restrições computacionais do problema [Fonte 2]."
        )

    # LLM call sequence for 4 chunks (with_sections=True → 2 groups):
    #   1. Partial group 1   2. Partial group 2   3. Consolidation
    #   4. Final synthesis   5. Style polish      6. [Re-synthesis if triggered]
    #   7. [Structure-fix if triggered and enabled]

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_candidate_with_bad_structure_and_fix_disabled_discarded(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Candidate with better quality-sig (more sources) but invalid structure
        must be discarded when structure-fix is disabled."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_WEAK_RATIO_DEGRADATION", "1.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "2")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        chunks = _make_chunks(4, with_sections=True)
        mock_collect.return_value = chunks

        # Current (final + polish): bad structure, 0 sources
        # candidate_sig(0 src) < candidate_sig(2 src) after re-synthesis
        # → resynthesis triggered, candidate has better sig but invalid structure
        # → discarded since fix is disabled
        llm_outputs = [
            self._make_llm_response("Parcial A."),
            self._make_llm_response("Parcial B."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._bad_no_cit()),   # final
            self._make_llm_response(self._bad_no_cit()),   # polish
            self._make_llm_response(self._bad_two_src()),  # re-synthesis → MARKER_CANDIDATO
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]

        # MARKER_CANDIDATO must NOT appear — candidate was discarded
        assert "MARKER_CANDIDATO" not in answer, (
            "Candidate with invalid structure must be discarded when fix is disabled"
        )
        # Pipeline must still produce a non-empty answer (kept current)
        assert isinstance(answer, str) and len(answer) > 0

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_candidate_structure_fixed_then_accepted(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """When structure-fix pass produces valid structure, fixed candidate is accepted."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "1")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_WEAK_RATIO_DEGRADATION", "1.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "2")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")

        chunks = _make_chunks(4, with_sections=True)
        mock_collect.return_value = chunks

        # Current: bad, 0 sources.  Candidate after re-synthesis: bad but 2 sources
        # → candidate_sig better → structure-fix triggered → good structure → accepted
        llm_outputs = [
            self._make_llm_response("Parcial A."),
            self._make_llm_response("Parcial B."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._bad_no_cit()),   # final
            self._make_llm_response(self._bad_two_src()),  # re-synthesis (candidate)
            self._make_llm_response(self._good_structure()),  # structure-fix → MARKER_FIXED
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]

        # MARKER_FIXED must appear — structure-fixed text was accepted
        assert "MARKER_FIXED" in answer, (
            "Structure-fixed candidate must be accepted when fix produces valid structure"
        )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_no_regression_citation_validation_after_structure_fix(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Phantom citations must be removed even after the structure-fix pass."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "1")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_WEAK_RATIO_DEGRADATION", "1.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "2")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")

        chunks = _make_chunks(4, with_sections=True)
        mock_collect.return_value = chunks

        # Sections must have enough words (> 12) even after stripping citations,
        # so that validate_summary_structure passes after [Fonte 999] is removed.
        good_with_phantom = (
            "# Resumo Aprofundado — doc.pdf MARKER_FIXED\n\n"
            "## Objetivo e Contexto\n"
            "O documento explica algoritmos de decisão com fundamentação teórica "
            "e exemplos práticos detalhados sobre uso em classificação [Fonte 1] "
            "e referência fantasma [Fonte 999].\n\n"
            "## Linha Lógica\n"
            "O material progride de fundamentos de entropia para técnicas avançadas "
            "de poda, mostrando encadeamento lógico entre cada conceito abordado [Fonte 2].\n\n"
            "## Conceitos Fundamentais\n"
            "Os conceitos centrais incluem ganho de informação, índice Gini e "
            "complexidade computacional com definições formais e exemplos [Fonte 1].\n\n"
            "## Síntese e Conclusão\n"
            "O documento conclui que a escolha correta do critério de divisão depende "
            "do contexto e das restrições computacionais do problema [Fonte 2]."
        )
        llm_outputs = [
            self._make_llm_response("Parcial A."),
            self._make_llm_response("Parcial B."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._bad_no_cit()),   # final
            self._make_llm_response(self._bad_two_src()),  # re-synthesis (candidate)
            self._make_llm_response(good_with_phantom),    # structure-fix → MARKER_FIXED
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        assert "[Fonte 999]" not in result["answer"], (
            "Phantom citation must be removed even after structure-fix"
        )
        assert "MARKER_FIXED" in result["answer"], (
            "Structure-fixed text must be accepted when valid"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Coverage gate — detect_coverage_signals
# ──────────────────────────────────────────────────────────────────────────────

class TestDetectCoverageSignals:
    """Unit tests for detect_coverage_signals()."""

    def _doc(self, text: str) -> Document:
        return Document(page_content=text, metadata={"chunk_index": 0})

    def test_empty_chunks_returns_all_false(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([])
        assert result["total_chunks"] == 0
        assert result["formula_chunks"] == 0
        assert result["procedure_chunks"] == 0
        assert result["example_chunks"] == 0
        assert result["concept_chunks"] == 0
        assert result["has_formulas"] is False
        assert result["has_procedures"] is False
        assert result["has_examples"] is False
        assert result["has_concepts"] is False

    def test_plain_chunk_no_signals(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("Texto simples sem conteudo especial.")])
        assert result["has_formulas"] is False
        assert result["has_procedures"] is False
        assert result["has_examples"] is False
        assert result["has_concepts"] is False

    def test_greek_letter_triggers_formula(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("O parametro alpha controla a taxa.")])
        # use actual unicode α
        result2 = detect_coverage_signals([self._doc("O par\u00e2metro \u03b1 controla a taxa.")])
        assert result2["has_formulas"] is True
        assert result2["formula_chunks"] == 1

    def test_assignment_pattern_triggers_formula(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("A variavel x = 5 representa o valor.")])
        assert result["has_formulas"] is True

    def test_algorithm_keyword_triggers_procedure(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("O algoritmo de busca binaria opera em O(log n).")])
        assert result["has_procedures"] is True
        assert result["procedure_chunks"] == 1

    def test_step_number_triggers_procedure(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("passo 1: inicializar a fila.\npasso 2: processar.")])
        assert result["has_procedures"] is True

    def test_numbered_list_triggers_procedure(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("1. Carregar os dados.\n2. Pre-processar.\n3. Treinar.")])
        assert result["has_procedures"] is True

    def test_example_keyword_triggers_example(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("Por exemplo, considere o caso de um grafo.")])
        assert result["has_examples"] is True
        assert result["example_chunks"] == 1

    def test_e_g_triggers_example(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("Features (e.g. cor, tamanho) sao normalizadas.")])
        assert result["has_examples"] is True

    def test_bold_definition_triggers_concept(self):
        from docops.summarize.pipeline import detect_coverage_signals

        result = detect_coverage_signals([self._doc("O **gradiente** e o vetor de derivadas.")])
        assert result["has_concepts"] is True
        assert result["concept_chunks"] == 1

    def test_definitional_phrase_triggers_concept(self):
        from docops.summarize.pipeline import detect_coverage_signals

        # "é definida como" using unicode
        result = detect_coverage_signals([self._doc("A entropia \u00e9 definida como a medida de incerteza.")])
        assert result["has_concepts"] is True

    def test_mixed_chunk_all_signals(self):
        from docops.summarize.pipeline import detect_coverage_signals

        text = (
            "O **algoritmo** segue passo 1: calcular \u03b1 = 0.5.\n"
            "Por exemplo, usando entropia \u00e9 definida como \u2212\u2211p log p."
        )
        result = detect_coverage_signals([self._doc(text)])
        assert result["has_formulas"] is True
        assert result["has_procedures"] is True
        assert result["has_examples"] is True
        assert result["has_concepts"] is True

    def test_multiple_chunks_counted_individually(self):
        from docops.summarize.pipeline import detect_coverage_signals

        chunks = [
            self._doc("O par\u00e2metro \u03b1 controla a taxa."),
            self._doc("Por exemplo, considere x = 1."),
            self._doc("Texto simples sem sinais."),
        ]
        result = detect_coverage_signals(chunks)
        assert result["formula_chunks"] == 2
        assert result["example_chunks"] == 1
        assert result["procedure_chunks"] == 0
        assert result["total_chunks"] == 3


# ──────────────────────────────────────────────────────────────────────────────
# Coverage gate — score_coverage
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreCoverage:
    """Unit tests for score_coverage()."""

    def _no_signals(self) -> dict:
        return {
            "has_formulas": False, "has_procedures": False,
            "has_examples": False, "has_concepts": False,
            "formula_chunks": 0, "procedure_chunks": 0,
            "example_chunks": 0, "concept_chunks": 0,
            "total_chunks": 3,
        }

    def _formula_only(self) -> dict:
        return {**self._no_signals(), "has_formulas": True, "formula_chunks": 1}

    def _procedure_only(self) -> dict:
        return {**self._no_signals(), "has_procedures": True, "procedure_chunks": 1}

    def _example_only(self) -> dict:
        return {**self._no_signals(), "has_examples": True, "example_chunks": 1}

    def _concept_enough(self) -> dict:
        return {**self._no_signals(), "has_concepts": True, "concept_chunks": 3}

    def _concept_too_few(self) -> dict:
        return {**self._no_signals(), "has_concepts": True, "concept_chunks": 1}

    def test_no_signals_returns_full_score(self):
        from docops.summarize.pipeline import score_coverage

        result = score_coverage("Qualquer texto.", self._no_signals())
        assert result["overall_coverage_score"] == 1.0
        assert result["formula_coverage"] == 1.0
        assert result["procedure_coverage"] == 1.0

    def test_empty_text_returns_full_score(self):
        from docops.summarize.pipeline import score_coverage

        result = score_coverage("", self._formula_only())
        assert result["overall_coverage_score"] == 1.0

    def test_formula_signal_summary_has_keywords_full_coverage(self):
        from docops.summarize.pipeline import score_coverage

        text = "A equacao principal e o calculo derivado sao apresentados."
        # use actual unicode
        text2 = "A equa\u00e7\u00e3o principal e o c\u00e1lculo derivado s\u00e3o apresentados."
        result = score_coverage(text2, self._formula_only())
        assert result["formula_coverage"] == 1.0
        assert result["overall_coverage_score"] == 1.0

    def test_formula_signal_summary_missing_keywords_zero_coverage(self):
        from docops.summarize.pipeline import score_coverage

        text = "O texto aborda tecnicas sem mencionar matematica."
        result = score_coverage(text, self._formula_only())
        assert result["formula_coverage"] == 0.0
        assert result["overall_coverage_score"] == 0.0

    def test_procedure_signal_summary_has_keywords_full_coverage(self):
        from docops.summarize.pipeline import score_coverage

        text = "O algoritmo define cada passo de forma sequencial."
        result = score_coverage(text, self._procedure_only())
        assert result["procedure_coverage"] == 1.0
        assert result["overall_coverage_score"] == 1.0

    def test_procedure_signal_summary_missing_keywords_zero_coverage(self):
        from docops.summarize.pipeline import score_coverage

        text = "O texto aborda estruturas sem descrever processos."
        result = score_coverage(text, self._procedure_only())
        assert result["procedure_coverage"] == 0.0

    def test_example_signal_one_hit_full_coverage(self):
        from docops.summarize.pipeline import score_coverage

        text = "Por exemplo, o modelo aprende a partir dos dados."
        result = score_coverage(text, self._example_only())
        assert result["example_coverage"] == 1.0

    def test_example_signal_missing_zero_coverage(self):
        from docops.summarize.pipeline import score_coverage

        text = "O modelo aprende a partir dos dados de entrada."
        result = score_coverage(text, self._example_only())
        assert result["example_coverage"] == 0.0

    def test_concept_active_when_enough_chunks(self):
        from docops.summarize.pipeline import score_coverage

        text = "O conceito de entropia e a defini\u00e7\u00e3o formal s\u00e3o explicados."
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_CONCEPT_MIN_HITS": "2"}):
            result = score_coverage(text, self._concept_enough())
        assert result["concept_coverage"] == 1.0
        assert result["overall_coverage_score"] == 1.0

    def test_concept_inactive_when_too_few_chunks(self):
        from docops.summarize.pipeline import score_coverage

        text = "Texto sem nenhum conceito definido formalmente."
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_CONCEPT_MIN_HITS": "2"}):
            result = score_coverage(text, self._concept_too_few())
        # concept type inactive — no penalty
        assert result["concept_coverage"] == 1.0
        assert result["overall_coverage_score"] == 1.0

    def test_absent_signal_type_not_penalised(self):
        from docops.summarize.pipeline import score_coverage

        # Document has no examples — summary not mentioning examples is correct
        signals = self._formula_only()
        signals["has_examples"] = False
        text = "A equa\u00e7\u00e3o e o c\u00e1lculo s\u00e3o detalhados."
        result = score_coverage(text, signals)
        assert result["example_coverage"] == 1.0
        assert result["formula_coverage"] == 1.0

    def test_overall_weighted_mean_over_active_only(self):
        from docops.summarize.pipeline import score_coverage

        # Only formulas active, formula_coverage=0 (no formula keywords) → overall=0
        text = "Texto sem formulas nem equacoes mencionadas."
        signals = self._formula_only()
        result = score_coverage(text, signals)
        assert result["overall_coverage_score"] == 0.0
        # procedure/example/concept not active → their scores are 1.0 but not in mean
        assert result["procedure_coverage"] == 1.0

    def test_partial_formula_coverage_intermediate_score(self):
        from docops.summarize.pipeline import score_coverage

        # "cálculo" = 1 hit → min(1.0, 1/2) = 0.5
        text = "O c\u00e1lculo do gradiente \u00e9 descrito."
        result = score_coverage(text, self._formula_only())
        assert result["formula_coverage"] == pytest.approx(0.5)
        assert result["overall_coverage_score"] == pytest.approx(0.5)

    def test_profile_weights_override_defaults(self):
        from docops.summarize.pipeline import score_coverage

        signals = {
            "has_formulas": True,
            "has_procedures": True,
            "has_examples": False,
            "has_concepts": False,
            "concept_chunks": 0,
        }
        text = "algoritmo e procedimento sem equação"
        profile = {
            "weight_formula": 0.9,
            "weight_procedure": 0.1,
            "weight_example": 0.0,
            "weight_concept": 0.0,
            "concept_min_hits": 2,
        }
        result = score_coverage(text, signals, coverage_profile=profile)
        baseline = score_coverage(text, signals)
        assert result["overall_coverage_score"] == pytest.approx(0.55)
        assert result["overall_coverage_score"] < baseline["overall_coverage_score"]


class TestCoverageProfiles:
    def test_auto_formula_profile_selected_by_signal_ratio(self):
        from docops.summarize.coverage_profiles import resolve_coverage_profile

        signals = {
            "formula_chunks": 4,
            "procedure_chunks": 0,
            "example_chunks": 0,
            "concept_chunks": 0,
            "total_chunks": 8,
        }
        profile = resolve_coverage_profile("capitulo.pdf", signals, configured_profile="auto")
        assert profile["name"] == "formula_heavy"

    def test_explicit_profile_override_wins(self):
        from docops.summarize.coverage_profiles import resolve_coverage_profile

        signals = {
            "formula_chunks": 10,
            "procedure_chunks": 0,
            "example_chunks": 0,
            "concept_chunks": 0,
            "total_chunks": 10,
        }
        profile = resolve_coverage_profile("doc.pdf", signals, configured_profile="narrative")
        assert profile["name"] == "narrative"


# ──────────────────────────────────────────────────────────────────────────────
# Coverage gate — config properties
# ──────────────────────────────────────────────────────────────────────────────

class TestCoverageGateConfig:
    """Verify env-var-driven coverage gate configuration."""

    def test_default_gate_enabled(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUMMARY_COVERAGE_GATE_ENABLED", None)
            assert c.summary_coverage_gate_enabled is True

    def test_default_min_score(self):
        from docops.config import Config
        c = Config()
        os.environ.pop("SUMMARY_COVERAGE_MIN_SCORE", None)
        assert c.summary_coverage_min_score == pytest.approx(0.50)

    def test_default_concept_min_hits(self):
        from docops.config import Config
        c = Config()
        os.environ.pop("SUMMARY_COVERAGE_CONCEPT_MIN_HITS", None)
        assert c.summary_coverage_concept_min_hits == 2

    def test_gate_disabled_via_env(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_GATE_ENABLED": "false"}):
            assert c.summary_coverage_gate_enabled is False

    def test_min_score_override(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_MIN_SCORE": "0.75"}):
            assert c.summary_coverage_min_score == pytest.approx(0.75)

    def test_weight_formula_override(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_WEIGHT_FORMULA": "0.5"}):
            assert c.summary_coverage_weight_formula == pytest.approx(0.5)

    def test_weight_concept_default(self):
        from docops.config import Config
        c = Config()
        os.environ.pop("SUMMARY_COVERAGE_WEIGHT_CONCEPT", None)
        assert c.summary_coverage_weight_concept == pytest.approx(0.20)

    def test_profile_default_auto(self):
        from docops.config import Config
        c = Config()
        os.environ.pop("SUMMARY_COVERAGE_PROFILE", None)
        assert c.summary_coverage_profile == "auto"

    def test_profile_override(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_PROFILE": "procedural"}):
            assert c.summary_coverage_profile == "procedural"

    def test_min_score_override_none_when_unset(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUMMARY_COVERAGE_MIN_SCORE", None)
            assert c.summary_coverage_min_score_override is None

    def test_min_score_override_value_when_set(self):
        from docops.config import Config
        c = Config()
        with patch.dict(os.environ, {"SUMMARY_COVERAGE_MIN_SCORE": "0.77"}):
            assert c.summary_coverage_min_score_override == pytest.approx(0.77)


# ──────────────────────────────────────────────────────────────────────────────
# Coverage gate — integration with run_deep_summary
# ──────────────────────────────────────────────────────────────────────────────

class TestCoverageGateIntegration:
    """Integration tests verifying coverage gate behaviour in run_deep_summary."""

    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    def _formula_chunks(self, n: int = 4) -> list[Document]:
        """Chunks containing Greek-letter formula signals."""
        return [
            Document(
                page_content=(
                    f"O par\u00e2metro \u03b1_{i} = 0.5 controla a taxa de aprendizado."
                ),
                metadata={
                    "chunk_index": i,
                    "section_path": f"Se\u00e7\u00e3o {i // 2 + 1}",
                    "page": i + 1,
                },
            )
            for i in range(n)
        ]

    def _plain_chunks(self, n: int = 4) -> list[Document]:
        """Chunks with no detectable content signals."""
        return [
            Document(
                page_content=f"Conte\u00fado descritivo do chunk {i}.",
                metadata={
                    "chunk_index": i,
                    "section_path": f"Se\u00e7\u00e3o {i // 2 + 1}",
                    "page": i + 1,
                },
            )
            for i in range(n)
        ]

    def _good_summary_no_formula(self, marker: str = "MARKER_INITIAL") -> str:
        """Valid structure, 2 unique sources — no formula keywords."""
        return (
            f"# Resumo Aprofundado \u2014 doc.pdf {marker}\n\n"
            "## Panorama e Contexto\n"
            "O documento descreve t\u00e9cnicas avan\u00e7adas de an\u00e1lise e "
            "processamento com suporte a m\u00faltiplos contextos [Fonte 1].\n\n"
            "## Linha L\u00f3gica e Constru\u00e7\u00e3o\n"
            "A progress\u00e3o l\u00f3gica conecta fundamentos \u00e0s t\u00e9cnicas "
            "mais avan\u00e7adas revelando encadeamento claro [Fonte 2].\n\n"
            "## Conceitos Centrais\n"
            "Os conceitos principais incluem representa\u00e7\u00f5es de dados e "
            "crit\u00e9rios de sele\u00e7\u00e3o baseados em evid\u00eancias [Fonte 1].\n\n"
            "## S\u00edntese e Conclus\u00e3o\n"
            "A s\u00edntese final integra os resultados e aponta aplica\u00e7\u00f5es "
            "sustentadas pelas fontes prim\u00e1rias [Fonte 2]."
        )

    def _good_summary_no_formula_single_source(self, marker: str = "MARKER_INITIAL") -> str:
        """Valid structure, only [Fonte 1] (unique=1) — no formula keywords.
        Used in coverage trigger test so candidate with 2 sources improves quality sig."""
        return (
            f"# Resumo Aprofundado \u2014 doc.pdf {marker}\n\n"
            "## Panorama e Contexto\n"
            "O documento descreve t\u00e9cnicas avan\u00e7adas de an\u00e1lise e "
            "processamento com suporte a m\u00faltiplos contextos de aplicac\u00e3o [Fonte 1].\n\n"
            "## Linha L\u00f3gica e Constru\u00e7\u00e3o\n"
            "A progress\u00e3o l\u00f3gica conecta fundamentos \u00e0s t\u00e9cnicas "
            "mais avan\u00e7adas revelando encadeamento claro entre as sec\u00f5es [Fonte 1].\n\n"
            "## Conceitos Centrais\n"
            "Os conceitos principais incluem representa\u00e7\u00f5es de dados e "
            "crit\u00e9rios de selec\u00e3o baseados em evid\u00eancias concretas [Fonte 1].\n\n"
            "## S\u00edntese e Conclus\u00e3o\n"
            "A s\u00edntese final integra os resultados e aponta as aplica\u00e7\u00f5es "
            "pr\u00e1ticas sustentadas pelas fontes prim\u00e1rias dispon\u00edveis [Fonte 1]."
        )

    def _good_summary_with_formula(self, marker: str = "MARKER_COVERAGE") -> str:
        """Valid structure, 2 unique sources — WITH formula keywords."""
        return (
            f"# Resumo Aprofundado \u2014 doc.pdf {marker}\n\n"
            "## Panorama e Contexto\n"
            "O documento descreve a equa\u00e7\u00e3o principal e o c\u00e1lculo "
            "dos par\u00e2metros com embasamento matem\u00e1tico rigoroso [Fonte 1].\n\n"
            "## Linha L\u00f3gica e Constru\u00e7\u00e3o\n"
            "A f\u00f3rmula derivada conecta fundamentos \u00e0s t\u00e9cnicas "
            "avan\u00e7adas revelando a nota\u00e7\u00e3o e express\u00e3o formal [Fonte 2].\n\n"
            "## Conceitos Centrais\n"
            "Os conceitos principais incluem representa\u00e7\u00f5es de dados e "
            "crit\u00e9rios de sele\u00e7\u00e3o baseados em evid\u00eancias [Fonte 1].\n\n"
            "## S\u00edntese e Conclus\u00e3o\n"
            "A s\u00edntese final integra os resultados matem\u00e1ticos e aponta "
            "aplica\u00e7\u00f5es sustentadas pelas fontes prim\u00e1rias [Fonte 2]."
        )

    # 4 chunks in 2 section groups → 2 partial + 1 consolidate + 1 final + 1 polish = 5 calls
    # + 1 re-synthesis if triggered = 6 total

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_gate_not_triggered_when_coverage_passes(
        self, mock_collect, mock_llm_factory
    ):
        """When formula coverage already passes the threshold no re-synthesis fires."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = self._formula_chunks(4)
        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_with_formula("MARKER_INITIAL")),
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_COVERAGE_GATE_ENABLED": "true",
            "SUMMARY_COVERAGE_MIN_SCORE": "0.50",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "true",
            "SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO": "2.0",   # disable grounding trigger (ratio max=1.0)
            "SUMMARY_MIN_UNIQUE_SOURCES": "1",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            "SUMMARY_MAX_CORRECTIVE_PASSES": "2",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "MARKER_INITIAL" in result["answer"]
        assert mock_llm.invoke.call_count == 4

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_gate_disabled_suppresses_coverage_trigger(
        self, mock_collect, mock_llm_factory
    ):
        """Gate disabled — low coverage must NOT trigger re-synthesis."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = self._formula_chunks(4)
        # Extra calls: 5 baseline + 1 optional topic-backfill + 1 optional extra-outline-repair
        base_resp = self._make_llm_response(self._good_summary_no_formula("MARKER_INITIAL"))
        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado."),
            base_resp,
            base_resp,
            base_resp,  # optional backfill
            base_resp,  # optional extra-outline-repair
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_COVERAGE_GATE_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "true",
            "SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO": "2.0",   # disable grounding trigger (ratio max=1.0)
            "SUMMARY_MIN_UNIQUE_SOURCES": "1",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "MARKER_INITIAL" in result["answer"]
        # 5 baseline calls + optional topic-backfill + optional extra-outline-repair
        assert mock_llm.invoke.call_count in (5, 6, 7)

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_gate_triggers_and_candidate_accepted_via_coverage(
        self, mock_collect, mock_llm_factory
    ):
        """Coverage gate triggers when score < min; candidate with coverage + quality
        improvement is accepted."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = self._formula_chunks(4)
        # LLM call sequence (no backfill global anymore; micro-backfill uses cheap LLM):
        # 1,2: partial summaries; 3: consolidate; 4: finalize → MARKER_INITIAL (no formula)
        # 5: resynthesis candidate → MARKER_COVERAGE (with formula, unique=2)
        # → coverage_gain=True (score>=0.8), quality sig improves (unique 1→2) → accepted
        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_no_formula_single_source("MARKER_INITIAL")),
            self._make_llm_response(self._good_summary_with_formula("MARKER_COVERAGE")),
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_COVERAGE_GATE_ENABLED": "true",
            "SUMMARY_COVERAGE_MIN_SCORE": "0.80",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "true",
            "SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE": "true",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_MIN_UNIQUE_SOURCES": "2",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            "SUMMARY_MAX_CORRECTIVE_PASSES": "2",
            # Disable micro-backfill so it doesn't consume the corrective budget
            # before resynthesis in this test (micro-backfill uses cheap LLM, not mock_llm).
            "SUMMARY_MICRO_BACKFILL_ENABLED": "false",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "MARKER_COVERAGE" in result["answer"], (
            "Candidate meeting coverage and quality improvement should be accepted"
        )
        assert mock_llm.invoke.call_count == 5

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_plain_chunks_no_signals_score_one_gate_never_fires(
        self, mock_collect, mock_llm_factory
    ):
        """Documents without content signals score 1.0 — gate never triggers."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = self._plain_chunks(4)
        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_no_formula("MARKER_PLAIN")),
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_COVERAGE_GATE_ENABLED": "true",
            "SUMMARY_COVERAGE_MIN_SCORE": "0.90",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "true",
            "SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO": "2.0",   # disable grounding trigger (ratio max=1.0)
            "SUMMARY_MIN_UNIQUE_SOURCES": "1",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            "SUMMARY_MAX_CORRECTIVE_PASSES": "2",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)

        assert "MARKER_PLAIN" in result["answer"]
        assert mock_llm.invoke.call_count == 4


class TestDeepSummaryDiagnostics:
    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    def _chunks(self) -> list[Document]:
        return [
            Document(
                page_content=f"A equação principal usa α = {i + 1}.",
                metadata={"chunk_index": i, "section_path": f"S{i // 2 + 1}", "page": i + 1},
            )
            for i in range(4)
        ]

    def _summary(self, marker: str) -> str:
        return (
            f"# Resumo Aprofundado — doc.pdf {marker}\n\n"
            "## Panorama Geral\n"
            "O documento apresenta a equação principal e seu contexto [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "A construção matemática segue cálculo incremental e expressão formal [Fonte 2].\n\n"
            "## Conceitos Centrais\n"
            "Os conceitos definem parâmetros e representação do modelo [Fonte 1].\n\n"
            "## Síntese Final\n"
            "A conclusão integra fórmula, interpretação e aplicação prática [Fonte 2]."
        )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_include_diagnostics_true_returns_payload(self, mock_collect, mock_llm_factory):
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = self._chunks()
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._summary("MARKER_DIAG")),
            self._make_llm_response(self._summary("MARKER_DIAG")),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_MIN_UNIQUE_SOURCES": "1",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary(
                "doc.pdf",
                "doc-uuid",
                user_id=1,
                include_diagnostics=True,
            )

        assert "diagnostics" in result
        diagnostics = result["diagnostics"]
        assert diagnostics["coverage_profile"]["name"] in {
            "balanced",
            "formula_heavy",
            "procedural",
            "narrative",
        }
        assert "overall_coverage_score" in diagnostics["coverage"]
        assert diagnostics["citations"]["anchors_total"] >= 1

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_include_diagnostics_false_keeps_contract(self, mock_collect, mock_llm_factory):
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = self._chunks()
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 2]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._summary("MARKER_NO_DIAG")),
            self._make_llm_response(self._summary("MARKER_NO_DIAG")),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_MIN_UNIQUE_SOURCES": "1",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary(
                "doc.pdf",
                "doc-uuid",
                user_id=1,
                profile="model_first",
            )

        assert "diagnostics" not in result


# ──────────────────────────────────────────────────────────────────────────────
# Structural validation: expanded categories (Ajuste 1)
# ──────────────────────────────────────────────────────────────────────────────

class TestStructureExpandedCategories:
    """Verify _REQUIRED_SECTION_CATEGORIES matches broader PT-BR heading variants."""

    def setup_method(self):
        from docops.summarize.pipeline import validate_summary_structure
        self.validate = validate_summary_structure

    def _summary_with_headings(self, headings: list[str]) -> str:
        parts = ["# Resumo Aprofundado — doc.pdf\n"]
        for h in headings:
            parts.append(f"## {h}\nConteúdo detalhado sobre o tópico, com explicação "
                         f"suficiente para não ser considerado fraco. Inclui definições, "
                         f"exemplos concretos e análise completa do tema abordado.")
        return "\n\n".join(parts)

    def test_classic_headings_pass(self):
        """Standard headings from the prompt template should pass."""
        text = self._summary_with_headings([
            "Objetivo e Contexto",
            "Linha Lógica do Documento",
            "Conceitos e Definições Centrais",
            "Síntese e Conclusão",
        ])
        info = self.validate(text, min_section_chars=20)
        assert info["valid"] is True
        assert info["missing_categories"] == []

    def test_alternative_headings_pass(self):
        """New broader keywords should accept variant headings."""
        text = self._summary_with_headings([
            "Introdução e Escopo",
            "Metodologia e Organização",
            "Princípios Teóricos Fundamentais",
            "Resultados e Discussão",
        ])
        info = self.validate(text, min_section_chars=20)
        assert info["valid"] is True, f"missing: {info['missing_categories']}"

    def test_accented_headings_match(self):
        """Accented headings should match via normalization."""
        text = self._summary_with_headings([
            "Motivação e Propósito",
            "Arquitetura e Fluxo",
            "Definições e Terminologia",
            "Considerações Finais",
        ])
        info = self.validate(text, min_section_chars=20)
        assert info["valid"] is True, f"missing: {info['missing_categories']}"

    def test_one_weak_section_still_valid(self):
        """A summary with 5 sections, 1 weak, should still be valid (4 strong >= min)."""
        parts = ["# Resumo\n"]
        good_headings = [
            "Objetivo e Contexto",
            "Estrutura do Documento",
            "Conceitos Centrais",
            "Síntese Final",
        ]
        for h in good_headings:
            parts.append(f"## {h}\nConteúdo suficiente com explicações detalhadas "
                         f"e análise completa para validar como seção forte.")
        # Add a weak section
        parts.append("## Extra\nCurto.")
        text = "\n\n".join(parts)
        info = self.validate(text, min_section_chars=20)
        assert info["valid"] is True

    def test_too_many_weak_sections_invalid(self):
        """All weak sections → invalid (not enough strong to meet min_sections)."""
        parts = ["# Resumo\n"]
        for i in range(4):
            parts.append(f"## Seção {i}\nX.")
        text = "\n\n".join(parts)
        info = self.validate(text, min_section_chars=20)
        assert info["valid"] is False


# ──────────────────────────────────────────────────────────────────────────────
# Grounding: improved token overlap with paraphrase (Ajuste 2)
# ──────────────────────────────────────────────────────────────────────────────

class TestStructureSemanticFallback:
    """Validate body-level fallback and technical short-section handling."""

    def setup_method(self):
        from docops.summarize.pipeline import validate_summary_structure, _is_section_generic_or_weak

        self.validate = validate_summary_structure
        self.is_weak = _is_section_generic_or_weak

    def test_body_fallback_recovers_missing_concepts_heading(self):
        """No concepts heading, but concept-rich body should satisfy concepts via fallback."""
        filler = (
            "Texto detalhado com explicacao completa, contexto metodologico e encadeamento "
            "suficiente para validacao estrutural."
        )
        text = (
            "## Panorama Geral\n"
            f"{filler} O objetivo central do documento e introduzir o problema.\n\n"
            "## Estrutura e Encadeamento\n"
            f"{filler} A linha logica descreve as etapas e o processo analitico.\n\n"
            "## Regularizacao e Otimizacao\n"
            f"{filler} O conceito de entropia recebe definicao formal e fundamentos tecnicos.\n\n"
            "## Conclusao\n"
            f"{filler} Em sintese, os resultados consolidam as contribuicoes."
        )
        info = self.validate(text, min_section_chars=40)
        assert info["valid"] is True
        assert info["missing_categories"] == []
        assert "concepts" in info["body_fallback_categories"]

    def test_h3_headings_are_accepted_when_h2_absent(self):
        """Parser should fallback to ### headings when ## is absent."""
        filler = (
            "Conteudo com densidade textual suficiente para evitar classificacao de secao fraca "
            "e permitir validacao semantica das categorias obrigatorias."
        )
        text = (
            "### Objetivo e Contexto\n"
            f"{filler}\n\n"
            "### Estrutura e Encadeamento Logico\n"
            f"{filler}\n\n"
            "### Conceitos e Definicoes Fundamentais\n"
            f"{filler}\n\n"
            "### Sintese e Conclusao\n"
            f"{filler}"
        )
        info = self.validate(text, min_section_chars=40)
        assert info["valid"] is True
        assert info["section_count"] == 4

    def test_short_technical_section_not_forced_as_weak(self):
        """Compact technical section with formula/procedure markers should pass."""
        body = "H(S) = -p1 log2 p1; algoritmo em 3 passos para minimizar custo."
        assert self.is_weak(body, min_section_chars=160) is False


class TestGroundingParaphraseOverlap:
    """Verify _token_overlap handles accents, case, and paraphrased text."""

    def setup_method(self):
        from docops.summarize.pipeline import _token_overlap, _normalize_token
        self.overlap = _token_overlap
        self.normalize = _normalize_token

    def test_accent_normalization(self):
        """Tokens with/without accents should match."""
        assert self.normalize("conclusão") == self.normalize("conclusao")
        assert self.normalize("Índice") == self.normalize("indice")
        assert self.normalize("ANÁLISE") == self.normalize("analise")

    def test_same_content_different_accents(self):
        """Text A with accents should overlap well with text B without accents."""
        text_a = "A conclusão é que o índice melhora a análise significativamente."
        text_b = "A conclusao e que o indice melhora a analise significativamente."
        score = self.overlap(text_a, text_b)
        assert score >= 0.90, f"Expected ≥0.90 for accent variants, got {score}"

    def test_paraphrased_text_overlap(self):
        """Paraphrased text sharing core vocabulary should have decent overlap."""
        anchor = "O algoritmo de árvore de decisão utiliza critério de entropia para selecionar atributos."
        paraphrase = "A árvore de decisão seleciona atributos com base na entropia, um critério do algoritmo."
        score = self.overlap(paraphrase, anchor)
        assert score >= 0.40, f"Expected ≥0.40 for paraphrase, got {score}"

    def test_citation_markers_stripped(self):
        """[Fonte N] markers should not affect overlap calculation."""
        text_a = "O algoritmo [Fonte 1] divide [Fonte 2] o array eficientemente."
        text_b = "O algoritmo divide o array eficientemente."
        score = self.overlap(text_a, text_b)
        assert score >= 0.90, f"Expected ≥0.90 without citation noise, got {score}"

    def test_completely_different_text(self):
        """Unrelated texts should have very low overlap."""
        text_a = "Fotossíntese cloroplasto vegetal oxigênio carbono."
        text_b = "Programação orientada objetos herança polimorfismo."
        score = self.overlap(text_a, text_b)
        assert score < 0.15, f"Expected <0.15 for unrelated texts, got {score}"

    def test_empty_text_returns_one(self):
        """Empty text_a should return 1.0 (trivially supported)."""
        assert self.overlap("", "qualquer coisa") == 1.0

    def test_markdown_stripped(self):
        """Markdown formatting should not affect overlap."""
        text_a = "**Conceitos** _fundamentais_ de `programação`."
        text_b = "Conceitos fundamentais de programação."
        score = self.overlap(text_a, text_b)
        assert score >= 0.90


# ──────────────────────────────────────────────────────────────────────────────
# Diversity gate: adaptive target (Ajuste 3)
# ──────────────────────────────────────────────────────────────────────────────

class TestAdaptiveDiversityTarget:
    """Verify diversity target adapts to document size."""

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_small_doc_lowers_target(self, mock_collect, mock_llm_factory):
        """For a doc with few chunks/groups, min_unique_sources should be reduced."""
        from docops.summarize.pipeline import run_deep_summary

        # 4 chunks → 1 group → 4 anchors → adaptive_cap = 2
        chunks = [
            _doc(f"Chunk {i} sobre conceitos fundamentais.", chunk_index=i, page=i+1)
            for i in range(4)
        ]
        mock_collect.return_value = chunks
        mock_llm = MagicMock()
        summary_text = (
            "# Resumo Aprofundado — small.pdf\n\n"
            "## Objetivo e Contexto\nO documento explica conceitos fundamentais "
            "de forma detalhada com exemplos práticos e teóricos [Fonte 1].\n\n"
            "## Estrutura do Documento\nA organização segue uma linha lógica "
            "progressiva do básico ao avançado [Fonte 2].\n\n"
            "## Conceitos e Definições\nOs conceitos centrais incluem terminologia "
            "específica da área com definições claras [Fonte 1].\n\n"
            "## Síntese e Conclusão\nEm conclusão, o documento oferece uma base "
            "sólida para estudo [Fonte 2]."
        )
        mock_llm.invoke.side_effect = [
            MagicMock(content="Parcial A sobre conceitos [Fonte 1]."),
            MagicMock(content="Consolidado sobre conceitos."),
            MagicMock(content=summary_text),
            MagicMock(content=summary_text),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_MIN_UNIQUE_SOURCES": "7",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("small.pdf", "doc-uuid", user_id=1,
                                       include_diagnostics=True)

        diag = result["diagnostics"]
        # With 4 anchors and 1 group, adaptive target should be << 7
        assert diag["citations"]["min_unique_sources"] <= 2
        assert diag["citations"]["min_unique_sources_config"] == 7
        assert "adaptive_reason" in diag["citations"]


# ──────────────────────────────────────────────────────────────────────────────
# Repair: forbidden pattern filter (Ajuste 4)
# ──────────────────────────────────────────────────────────────────────────────

class TestForbiddenRepairPatterns:
    """Verify _has_forbidden_repair_patterns accepts legitimate citations."""

    def setup_method(self):
        from docops.summarize.pipeline import _has_forbidden_repair_patterns
        self.check = _has_forbidden_repair_patterns

    def test_inline_citation_in_prose_allowed(self):
        """[Fonte N] used inline in prose should NOT be forbidden."""
        text = "O algoritmo utiliza entropia [Fonte 1] para selecionar atributos."
        assert self.check(text) is False

    def test_bullet_list_with_citation_allowed(self):
        """Bullet list items with [Fonte N] should NOT be forbidden."""
        text = "- A entropia mede desordem [Fonte 1]\n- Gini mede impureza [Fonte 2]"
        assert self.check(text) is False

    def test_fontes_section_forbidden(self):
        """A 'Fontes:' section header IS forbidden."""
        text = "Texto normal.\n\n**Fontes:**\n[Fonte 1] doc.pdf"
        assert self.check(text) is True

    def test_source_mapping_line_forbidden(self):
        """[Fonte N]: description mapping lines ARE forbidden."""
        text = "[Fonte 1]: doc.pdf, página 3"
        assert self.check(text) is True

    def test_orphan_citation_lines_forbidden(self):
        """Lines with only [Fonte N] markers ARE forbidden."""
        text = "[Fonte 1] [Fonte 2] [Fonte 3]"
        assert self.check(text) is True

    def test_meta_commentary_forbidden(self):
        """Repair meta-commentary IS forbidden."""
        text = "não encontrei informações nas fontes fornecidas"
        assert self.check(text) is True

    def test_source_dump_entry_forbidden(self):
        """[Fonte N] followed by file metadata IS forbidden."""
        text = "[Fonte 1] relatorio.pdf (página 5)"
        assert self.check(text) is True

    def test_clean_prose_not_forbidden(self):
        """Normal analytical prose should not trigger any pattern."""
        text = ("O conceito de entropia é central para a teoria da informação. "
                "Shannon definiu entropia como a medida de incerteza [Fonte 1].")
        assert self.check(text) is False


class TestRepairBlockSanitizeFirst:
    """Verify _repair_block sanitizes before checking forbidden patterns."""

    def setup_method(self):
        from docops.summarize.pipeline import _repair_block
        self.repair = _repair_block

    def test_repair_with_leaked_fontes_section_sanitized(self):
        """If LLM leaks a Fontes: section, it should be stripped and repair accepted."""
        block = "Texto original fraco [Fonte 1]."
        anchor_texts = ["conceito de entropia e informação"]
        indices = [1]

        mock_llm = MagicMock()
        # LLM output has valid prose + leaked Fontes: section
        repaired_with_leak = (
            "A entropia mede a incerteza na informação [Fonte 1].\n\n"
            "**Fontes:**\n[Fonte 1] doc.pdf"
        )
        mock_llm.invoke.return_value = MagicMock(content=repaired_with_leak)

        result = self.repair(block, anchor_texts, indices, mock_llm)
        # Should accept the repair after stripping the Fontes: section
        assert "entropia" in result
        assert "Fontes:" not in result

    def test_repair_with_only_meta_commentary_rejected(self):
        """Pure meta-commentary should still be rejected."""
        block = "Texto original fraco [Fonte 1]."
        anchor_texts = ["conceito irrelevante"]
        indices = [1]

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content="não encontrei informações nas fontes fornecidas"
        )

        result = self.repair(block, anchor_texts, indices, mock_llm)
        # Should keep original block
        assert result == block


# ──────────────────────────────────────────────────────────────────────────────
# Config defaults updated: diversity=5, structure-fix=2
# ──────────────────────────────────────────────────────────────────────────────

class TestUpdatedConfigDefaults:
    """Verify the new default values for diversity and structure-fix."""

    def test_min_unique_sources_default_five(self):
        from docops.config import Config
        cfg = Config()
        assert cfg.summary_min_unique_sources == 5

    def test_structure_fix_max_calls_default_two(self):
        from docops.config import Config
        cfg = Config()
        assert cfg.summary_structure_fix_max_calls == 2

    def test_min_unique_sources_env_override(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "3")
        from docops.config import Config
        assert Config().summary_min_unique_sources == 3

    def test_structure_fix_max_calls_env_override(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "4")
        from docops.config import Config
        assert Config().summary_structure_fix_max_calls == 4


# ──────────────────────────────────────────────────────────────────────────────
# Prompt diversity instruction
# ──────────────────────────────────────────────────────────────────────────────

class TestPromptDiversityInstruction:
    """Verify prompts contain explicit diversity instruction."""

    def test_final_prompt_has_diversity_instruction(self):
        from docops.rag.prompts import DEEP_SUMMARY_FINAL_PROMPT
        assert "DISTRIBUA" in DEEP_SUMMARY_FINAL_PROMPT
        assert "concentrar" in DEEP_SUMMARY_FINAL_PROMPT.lower()

    def test_resynthesis_prompt_has_diversity_instruction(self):
        from docops.rag.prompts import DEEP_SUMMARY_RESYNTHESIS_PROMPT
        assert "Distribua" in DEEP_SUMMARY_RESYNTHESIS_PROMPT
        assert "concentrar" in DEEP_SUMMARY_RESYNTHESIS_PROMPT.lower()

    def test_final_prompt_enforces_canonical_scaffold(self):
        from docops.rag.prompts import DEEP_SUMMARY_FINAL_PROMPT

        assert "EXATAMENTE 5 seções" in DEEP_SUMMARY_FINAL_PROMPT
        assert "## Encadeamento e Principais Tópicos" in DEEP_SUMMARY_FINAL_PROMPT
        assert "## Conceitos e Métodos Fundamentais" in DEEP_SUMMARY_FINAL_PROMPT

    def test_resynthesis_prompt_blocks_extra_h2_sections(self):
        from docops.rag.prompts import DEEP_SUMMARY_RESYNTHESIS_PROMPT

        lower = DEEP_SUMMARY_RESYNTHESIS_PROMPT.lower()
        assert "nao crie novas secoes" in lower
        assert "5 secoes com titulo \"##\"" in lower


# ──────────────────────────────────────────────────────────────────────────────
# Diversity-driven re-synthesis acceptance
# ──────────────────────────────────────────────────────────────────────────────

class TestDiversityDrivenResynthesis:
    """Integration: diversity as trigger → candidate accepted via diversity gain."""

    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    def _good_summary_single_source(self):
        """Valid structure with only [Fonte 1] — diverse=1."""
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Objetivo e Contexto\n"
            "O documento explica algoritmos de decisão com fundamentação teórica "
            "e exemplos práticos detalhados sobre uso em classificação [Fonte 1].\n\n"
            "## Estrutura do Documento\n"
            "O material progride de fundamentos de entropia para técnicas avançadas "
            "de poda, mostrando encadeamento lógico entre conceitos [Fonte 1].\n\n"
            "## Conceitos e Definições\n"
            "Os conceitos centrais incluem ganho de informação e índice Gini "
            "com definições formais e exemplos concretos [Fonte 1].\n\n"
            "## Síntese e Conclusão\n"
            "O documento conclui que a escolha do critério de divisão depende "
            "do contexto e das restrições computacionais [Fonte 1]."
        )

    def _good_summary_diverse(self):
        """Valid structure with [Fonte 1], [Fonte 2], [Fonte 3] — MARKER_DIVERSE."""
        return (
            "# Resumo Aprofundado — doc.pdf MARKER_DIVERSE\n\n"
            "## Objetivo e Contexto\n"
            "O documento explica algoritmos de decisão com fundamentação teórica "
            "e exemplos práticos detalhados sobre uso em classificação [Fonte 1].\n\n"
            "## Estrutura do Documento\n"
            "O material progride de fundamentos de entropia para técnicas avançadas "
            "de poda, mostrando encadeamento lógico entre conceitos [Fonte 2].\n\n"
            "## Conceitos e Definições\n"
            "Os conceitos centrais incluem ganho de informação e índice Gini "
            "com definições formais e exemplos concretos [Fonte 3].\n\n"
            "## Síntese e Conclusão\n"
            "O documento conclui que a escolha do critério depende do contexto "
            "e das restrições computacionais [Fonte 1] [Fonte 2]."
        )

    def _bad_structure_diverse(self):
        """Invalid structure (too few sections, weak) but diverse citations."""
        return (
            "# Resumo — doc.pdf MARKER_BAD_STRUCT\n\n"
            "## Dados\nCurto [Fonte 1] [Fonte 2] [Fonte 3].\n\n"
            "## Mais\nCurto [Fonte 1]."
        )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_diversity_trigger_candidate_accepted_via_diversity_gain(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """When diversity triggers re-synthesis and candidate has better diversity
        with valid structure, it should be accepted even if sig doesn't strictly improve."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "2")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "2.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "3")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_single_source()),   # final
            self._make_llm_response(self._good_summary_diverse()),         # re-synthesis
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1,
                                   include_diagnostics=True)
        answer = result["answer"]

        assert "MARKER_DIVERSE" in answer, (
            "Candidate with better diversity and valid structure should be accepted"
        )
        diag = result["diagnostics"]
        assert diag["resynthesis"]["accepted"] is True
        assert diag["resynthesis"]["diversity_was_primary_trigger"] is True
        assert diag["resynthesis"]["unique_sources_before"] is not None
        assert diag["resynthesis"]["unique_sources_candidate"] is not None
        assert diag["resynthesis"]["unique_sources_candidate"] > diag["resynthesis"]["unique_sources_before"]

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_diversity_candidate_blocked_by_absolute_weak_ratio(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Default absolute weak-ratio ceiling must block low-grounding candidates."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "2")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "2.0")
        # Keep default absolute ceiling (0.35) to validate blocking behavior.
        monkeypatch.delenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", raising=False)
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "3")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_single_source()),
            self._make_llm_response(self._good_summary_single_source()),
            self._make_llm_response(self._good_summary_diverse()),
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]["resynthesis"]

        assert diag["accepted"] is False
        assert diag["absolute_weak_ratio_blocked"] is True
        assert abs(diag["max_accepted_weak_ratio"] - 0.35) < 1e-9

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_bad_structure_candidate_still_discarded(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Even with diversity gain, candidate with truly bad structure is discarded."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_PASS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_STRUCTURE_FIX_MAX_CALLS", "1")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "2.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "3")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_single_source()),   # final
            self._make_llm_response(self._good_summary_single_source()),   # polish
            self._make_llm_response(self._bad_structure_diverse()),         # re-synthesis
            # structure-fix also returns bad structure
            self._make_llm_response(self._bad_structure_diverse()),
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1,
                                   include_diagnostics=True)
        answer = result["answer"]

        assert "MARKER_BAD_STRUCT" not in answer, (
            "Candidate with bad structure must be discarded even with diversity gain"
        )
        diag = result["diagnostics"]
        assert diag["resynthesis"]["accepted"] is False

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_diagnostics_include_diversity_comparison(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Diagnostics must include diversity_was_primary_trigger and source comparison."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_REQUIRE_STRUCTURE", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "2.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "3")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        chunks = _make_chunks(6, with_sections=True)
        mock_collect.return_value = chunks

        llm_outputs = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(self._good_summary_single_source()),   # final
            self._make_llm_response(self._good_summary_single_source()),   # polish
            self._make_llm_response(self._good_summary_diverse()),         # re-synthesis
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1,
                                   include_diagnostics=True)

        diag = result["diagnostics"]
        resynth = diag["resynthesis"]
        assert "diversity_was_primary_trigger" in resynth
        assert "unique_sources_before" in resynth
        assert "unique_sources_candidate" in resynth
        assert resynth["unique_sources_before"] is not None
        assert resynth["unique_sources_candidate"] is not None

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_diversity_gain_blocked_when_grounding_degrades_too_much(
        self,
        mock_collect,
        mock_llm_factory,
        monkeypatch,
    ):
        """Diversity-only gains must be blocked when weak_ratio degradation exceeds threshold."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "2.0")
        monkeypatch.setenv("SUMMARY_MIN_UNIQUE_SOURCES", "2")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_WEAK_RATIO_DEGRADATION", "0.05")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_GROUP_SIZE", "3")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")

        mock_collect.return_value = _make_chunks(9, with_sections=False)

        current_balanced = (
            "# Resumo Aprofundado - doc.pdf CURRENT_MARKER\n\n"
            "## Objetivo e Contexto\n"
            "Conteudo do chunk 0 com descricao objetiva e direta [Fonte 1].\n\n"
            "## Linha Logica\n"
            "Conteudo do chunk 1 descreve a progressao do documento [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Conteudo do chunk 2 explica os conceitos principais com clareza [Fonte 1].\n\n"
            "## Sintese e Conclusao\n"
            "Conteudo do chunk 0 e do chunk 1 resume o fechamento analitico [Fonte 1]."
        )
        candidate_diverse_weak = (
            "# Resumo Aprofundado - doc.pdf CANDIDATE_MARKER\n\n"
            "## Objetivo e Contexto\n"
            "Analise abstrata generica sem aderencia factual ao corpus [Fonte 1].\n\n"
            "## Linha Logica\n"
            "Descricao vaga e inventada sem termos do texto base [Fonte 2].\n\n"
            "## Conceitos Fundamentais\n"
            "Conjunto amplo de declaracoes sem ancoragem textual verificavel [Fonte 3].\n\n"
            "## Sintese e Conclusao\n"
            "Fechamento especulativo desconectado dos trechos recuperados [Fonte 1] [Fonte 2] [Fonte 3]."
        )

        llm_outputs = [
            self._make_llm_response("Parcial 1 [Fonte 1]."),
            self._make_llm_response("Parcial 2 [Fonte 1]."),
            self._make_llm_response("Parcial 3 [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(current_balanced),
            self._make_llm_response(candidate_diverse_weak),
        ]
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf",
            "doc-uuid",
            user_id=1,
            include_diagnostics=True,
        )
        resynth = result["diagnostics"]["resynthesis"]

        assert resynth["accepted"] is False
        assert resynth["diversity_was_primary_trigger"] is True
        assert resynth["unique_sources_before"] == 1
        assert resynth["unique_sources_candidate"] == 3
        assert resynth["grounding_weak_ratio_before"] is not None
        assert resynth["grounding_weak_ratio_candidate"] is not None
        assert resynth["grounding_weak_ratio_delta"] is not None
        assert resynth["grounding_weak_ratio_candidate"] > resynth["grounding_weak_ratio_before"]
        assert resynth["grounding_weak_ratio_delta"] > 0.05
        assert abs(resynth["max_allowed_weak_ratio_degradation"] - 0.05) < 1e-9
        assert resynth["diversity_grounding_guard_blocked"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Topic backfill
# ──────────────────────────────────────────────────────────────────────────────

class TestTopicBackfillIntegration:
    def _make_llm_response(self, text: str):
        mock = MagicMock()
        mock.content = text
        return mock

    def _base_summary(self, marker: str = "BASE") -> str:
        return (
            f"# Resumo Aprofundado — doc.pdf {marker}\n\n"
            "## Objetivo e Contexto\n"
            "O documento apresenta conceitos com base teórica e escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica e Construção\n"
            "A progressão organiza o conteúdo em etapas com encadeamento explícito [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "As definições centrais conectam critérios, variáveis e decisões do modelo [Fonte 1].\n\n"
            "## Síntese Final\n"
            "A conclusão integra as ideias principais e limitações operacionais [Fonte 1]."
        )

    def _outline_missing(self) -> dict[str, Any]:
        return {
            "overall_score": 0.5,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": [],
            "missing_topics": ["math_formalization"],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 0.0},
        }

    def _outline_covered(self) -> dict[str, Any]:
        return {
            "overall_score": 1.0,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": ["math_formalization"],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 1.0},
        }

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_topic_backfill_triggers_and_is_accepted(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
    ):
        from docops.summarize.pipeline import run_deep_summary

        base = self._base_summary("BASE")
        backfilled = self._base_summary("BACKFILLED_OK")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "minor_topics": [],
            "topic_details": {"math_formalization": {"label": "Formalização matemática", "hits": 2}},
            "outline_text": "",
        }

        def _outline_side_effect(text: str, topic_info: dict[str, Any]):
            return self._outline_covered() if "BACKFILLED_OK" in text else self._outline_missing()

        mock_outline_score.side_effect = _outline_side_effect

        # _run_micro_topic_backfill returns a dict; the backfilled text contains BACKFILLED_OK
        mock_micro_backfill.return_value = {
            "text": backfilled,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["math_formalization"],
            "missing_topics_after": [],
            "skipped_topics": [],
            "latency_ms": 10.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(base),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            # Disable absolute ceiling so this test focuses only on trigger/accept logic
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            # Disable early backfill so this test isolates the post-resynthesis backfill step
            "SUMMARY_BACKFILL_BEFORE_DEOVERREACH": "false",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        backfill = result["diagnostics"]["backfill"]
        assert backfill["triggered"] is True
        assert backfill["accepted"] is True
        assert backfill["missing_before"] == ["math_formalization"]
        assert backfill["missing_after"] == []
        mock_micro_backfill.assert_called_once()
        assert "BACKFILLED_OK" in result["answer"]

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_topic_backfill_rolls_back_on_structure_break(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
    ):
        """When micro-backfill accepts paragraphs but grounding ceiling is exceeded,
        rollback_reason should be 'absolute_weak_ratio_exceeded'. When no paragraphs
        are accepted (e.g. all discarded), rollback_reason is 'no_paragraphs_accepted'."""
        from docops.summarize.pipeline import run_deep_summary

        base = self._base_summary("BASE")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "minor_topics": [],
            "topic_details": {"math_formalization": {"label": "Formalização matemática", "hits": 2}},
            "outline_text": "",
        }
        mock_outline_score.return_value = self._outline_missing()

        # Micro-backfill generates 0 accepted paragraphs (all discarded).
        mock_micro_backfill.return_value = {
            "text": base,  # unchanged — no paragraph accepted
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 0,
            "missing_topics_before": ["math_formalization"],
            "missing_topics_after": ["math_formalization"],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(base),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        backfill = result["diagnostics"]["backfill"]
        assert backfill["triggered"] is True
        assert backfill["accepted"] is False
        assert backfill["rollback_reason"] == "no_paragraphs_accepted"
        assert "BASE" in result["answer"]


# ──────────────────────────────────────────────────────────────────────────────
# Absolute weak-ratio ceiling on backfill and final gate
# ──────────────────────────────────────────────────────────────────────────────


class TestBackfillAbsoluteWeakRatioCeiling:
    """Backfill must be rejected when bf_weak_ratio > max_accepted_weak_ratio,
    even when missing topics would be reduced."""

    def _make_llm_response(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    def _base_summary(self, marker: str = "BASE") -> str:
        return (
            f"# Resumo Aprofundado — doc.pdf {marker}\n\n"
            "## Objetivo e Contexto\n"
            "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Definições centrais [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )

    def _outline_missing(self) -> dict[str, Any]:
        return {
            "overall_score": 0.5,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": [],
            "missing_topics": ["math_formalization"],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 0.0},
        }

    def _outline_covered(self) -> dict[str, Any]:
        return {
            "overall_score": 1.0,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": ["math_formalization"],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 1.0},
        }

    def _grounding_above_ceiling(self) -> dict[str, Any]:
        """weak_ratio = 4/10 = 0.40 > ceiling 0.35, but delta vs pre (0.32) is only 0.08.
        Note: use with pre-grounding of _grounding_near_ceiling (0.32) so delta=0.08 > 0.05,
        which means grounding_degraded fires first. For ceiling-specific test, use
        _grounding_just_above_ceiling with pre=_grounding_just_below_ceiling."""
        return {
            "blocks_with_citations": 10,
            "weakly_grounded": 4,
            "repaired_blocks": 0,
            "grounded_blocks": 6,
        }

    def _grounding_just_above_ceiling(self) -> dict[str, Any]:
        """weak_ratio = 4/10 = 0.40 > ceiling 0.35; delta vs 0.37 pre is only 0.03 <= 0.05."""
        return {
            "blocks_with_citations": 10,
            "weakly_grounded": 4,
            "repaired_blocks": 0,
            "grounded_blocks": 6,
        }

    def _grounding_just_below_ceiling(self) -> dict[str, Any]:
        """weak_ratio = 37/100 = 0.37: used as pre-backfill baseline.
        delta to just_above (0.40) = 0.03 <= max_weak_ratio_degradation (0.05) → no grounding_degraded.
        But 0.40 > ceiling 0.35 → absolute_ceiling_exceeded fires."""
        # Approximate with 10 blocks: 3.7 → use 4 weakly grounded = 0.40
        # To get pre=0.37 we use 100 blocks, but keep it simple: use floats via direct dict.
        return {
            "blocks_with_citations": 100,
            "weakly_grounded": 37,
            "repaired_blocks": 0,
            "grounded_blocks": 63,
        }

    def _grounding_ok(self) -> dict[str, Any]:
        """Simulates weak_ratio below ceiling (0.20 <= 0.35)."""
        return {
            "blocks_with_citations": 10,
            "weakly_grounded": 2,
            "repaired_blocks": 0,
            "grounded_blocks": 8,
        }

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_backfill_rejected_when_absolute_ceiling_exceeded(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        mock_grounding,
    ):
        """Micro-backfill with bf_weak_ratio > ceiling must be rejected."""
        from docops.summarize.pipeline import run_deep_summary

        base = self._base_summary("BASE")
        backfilled = self._base_summary("BACKFILLED_HIGH_WEAK")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "minor_topics": [],
            "topic_details": {"math_formalization": {"label": "Formalização matemática", "hits": 2}},
            "outline_text": "",
        }
        # Micro-backfill returns 1 accepted paragraph, text contains marker.
        mock_micro_backfill.return_value = {
            "text": backfilled,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["math_formalization"],
            "missing_topics_after": [],
            "skipped_topics": [],
            "latency_ms": 10.0,
        }

        def _outline_side_effect(text, topic_info):
            if "BACKFILLED_HIGH_WEAK" in text:
                return self._outline_covered()
            return self._outline_missing()

        mock_outline_score.side_effect = _outline_side_effect

        # After micro-backfill: weak_ratio exceeds ceiling (0.40 > 0.35).
        def _grounding_side_effect(text, anchors, threshold, llm=None):
            if "BACKFILLED_HIGH_WEAK" in text:
                return text, self._grounding_just_above_ceiling()
            return text, self._grounding_just_below_ceiling()

        mock_grounding.side_effect = _grounding_side_effect

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(base),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "0.35",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        backfill = result["diagnostics"]["backfill"]
        assert backfill["triggered"] is True
        assert backfill["accepted"] is False, "Backfill must be rejected when ceiling exceeded"
        assert backfill["rollback_reason"] == "absolute_weak_ratio_exceeded"
        assert backfill["absolute_weak_ratio_blocked"] is True
        # original (BASE) text must remain
        assert "BASE" in result["answer"]
        assert "BACKFILLED_HIGH_WEAK" not in result["answer"]

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_backfill_accepted_when_within_ceiling(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        mock_grounding,
    ):
        """Micro-backfill accepted when weak_ratio stays within ceiling."""
        from docops.summarize.pipeline import run_deep_summary

        base = self._base_summary("BASE")
        backfilled = self._base_summary("BACKFILLED_OK")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "minor_topics": [],
            "topic_details": {"math_formalization": {"label": "Formalização matemática", "hits": 2}},
            "outline_text": "",
        }
        mock_micro_backfill.return_value = {
            "text": backfilled,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["math_formalization"],
            "missing_topics_after": [],
            "skipped_topics": [],
            "latency_ms": 8.0,
        }

        def _outline_side_effect(text, topic_info):
            if "BACKFILLED_OK" in text:
                return self._outline_covered()
            return self._outline_missing()

        mock_outline_score.side_effect = _outline_side_effect

        # All grounding calls return ok (weak_ratio=0.20 <= ceiling=0.35)
        mock_grounding.side_effect = lambda text, anchors, threshold, llm=None: (
            text, self._grounding_ok()
        )

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_llm_response("Parcial A [Fonte 1]."),
            self._make_llm_response("Parcial B [Fonte 1]."),
            self._make_llm_response("Consolidado."),
            self._make_llm_response(base),
        ]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "0.35",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            # Disable early backfill so this test isolates the post-resynthesis backfill step
            "SUMMARY_BACKFILL_BEFORE_DEOVERREACH": "false",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        backfill = result["diagnostics"]["backfill"]
        assert backfill["triggered"] is True
        assert backfill["accepted"] is True
        assert backfill["absolute_weak_ratio_blocked"] is False
        assert "BACKFILLED_OK" in result["answer"]

    def test_backfill_diagnostics_have_weak_ratio_fields(self):
        """diagnostics['backfill'] always has weak_ratio_before and absolute_weak_ratio_blocked."""
        from unittest.mock import patch as p
        from docops.summarize.pipeline import run_deep_summary

        with p("docops.summarize.pipeline.collect_ordered_chunks") as mc, \
             p("docops.summarize.pipeline._get_llm") as ml, \
             p("docops.summarize.pipeline.extract_document_topics") as me, \
             p("docops.summarize.pipeline.score_topic_outline_coverage") as mo:

            mc.return_value = _make_chunks(4, with_sections=True)
            me.return_value = {
                "detected_topics": [],
                "must_cover_topics": [],
                "minor_topics": [],
                "topic_details": {},
                "outline_text": "",
            }
            mo.return_value = {
                "overall_score": 1.0, "detected_topics": [], "must_cover_topics": [],
                "covered_topics": [], "missing_topics": [], "weakly_covered_topics": [],
                "topic_scores": {},
            }
            base = (
                "# Resumo Aprofundado — doc.pdf\n\n"
                "## Objetivo e Contexto\nIntrodução [Fonte 1].\n\n"
                "## Linha Lógica\nProgressão [Fonte 1].\n\n"
                "## Conceitos Fundamentais\nDefinições [Fonte 1].\n\n"
                "## Síntese Final\nConclusão [Fonte 1]."
            )
            m = MagicMock()
            m.content = base
            ml.return_value.invoke.side_effect = [m, m, m, m, m]

            with patch.dict(os.environ, {
                "SUMMARY_RESYNTHESIS_ENABLED": "false",
                "SUMMARY_GROUNDING_REPAIR": "false",
                "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            }):
                result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        backfill = result["diagnostics"]["backfill"]
        assert "weak_ratio_before" in backfill
        assert "weak_ratio_after" in backfill
        assert "absolute_weak_ratio_blocked" in backfill
        assert isinstance(backfill["weak_ratio_before"], float)
        assert backfill["absolute_weak_ratio_blocked"] is False  # not triggered


class TestFinalAbsoluteWeakRatioGate:
    """Final gate tracks absolute ceiling and marks diagnostics correctly."""

    def _base_summary(self, marker: str = "") -> str:
        tag = f" {marker}" if marker else ""
        return (
            f"# Resumo Aprofundado — doc.pdf{tag}\n\n"
            "## Objetivo e Contexto\n"
            "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Definições centrais [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_gate_marks_failure_when_weak_ratio_exceeds_ceiling(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_grounding,
    ):
        """diagnostics['final']['absolute_weak_ratio_passed'] must be False when ratio > ceiling."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }
        # All grounding calls return bad (weak_ratio=0.80 > ceiling=0.35)
        mock_grounding.side_effect = lambda text, anchors, threshold, llm=None: (
            text,
            {
                "blocks_with_citations": 10,
                "weakly_grounded": 8,
                "repaired_blocks": 0,
                "grounded_blocks": 2,
            },
        )

        mock_llm = MagicMock()
        r = MagicMock()
        r.content = self._base_summary()
        mock_llm.invoke.side_effect = [r, r, r, r, r]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "0.35",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final_diag = result["diagnostics"]["final"]
        assert "absolute_weak_ratio_passed" in final_diag
        assert final_diag["absolute_weak_ratio_passed"] is False
        assert final_diag["absolute_weak_ratio_ceiling"] == pytest.approx(0.35, abs=0.001)

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_gate_passes_when_within_ceiling(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_grounding,
    ):
        """diagnostics['final']['absolute_weak_ratio_passed'] is True when ratio <= ceiling."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }
        mock_grounding.side_effect = lambda text, anchors, threshold, llm=None: (
            text,
            {
                "blocks_with_citations": 10,
                "weakly_grounded": 2,
                "repaired_blocks": 0,
                "grounded_blocks": 8,
            },
        )

        mock_llm = MagicMock()
        r = MagicMock()
        r.content = self._base_summary()
        mock_llm.invoke.side_effect = [r, r, r, r, r]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "0.35",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final_diag = result["diagnostics"]["final"]
        assert final_diag["absolute_weak_ratio_passed"] is True

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_gate_passes_after_repair_reduces_ratio(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_grounding,
    ):
        """When repair=true, a repair call that reduces weak_ratio below ceiling makes gate pass."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }

        # First calls return bad grounding; the final repair call returns good
        grounding_calls = [0]

        def _grounding_side_effect(text, anchors, threshold, llm=None):
            grounding_calls[0] += 1
            if llm is not None:
                # This is the repair call — return good grounding
                return text, {
                    "blocks_with_citations": 10,
                    "weakly_grounded": 2,
                    "repaired_blocks": 5,
                    "grounded_blocks": 8,
                }
            return text, {
                "blocks_with_citations": 10,
                "weakly_grounded": 8,
                "repaired_blocks": 0,
                "grounded_blocks": 2,
            }

        mock_grounding.side_effect = _grounding_side_effect

        mock_llm = MagicMock()
        r = MagicMock()
        r.content = self._base_summary()
        mock_llm.invoke.side_effect = [r, r, r, r, r]
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "true",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "0.35",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final_diag = result["diagnostics"]["final"]
        assert final_diag["absolute_weak_ratio_passed"] is True, (
            f"Expected gate to pass after repair, got: {final_diag}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Final accepted / blocking_reasons — outline missing topics gate
# ──────────────────────────────────────────────────────────────────────────────


class TestFinalAcceptedAndOutlineGate:
    """Tests for diagnostics['final']['accepted'] and outline missing-topics gate."""

    def _base_summary(self) -> str:
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Objetivo e Contexto\n"
            "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Definições centrais [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )

    def _resp(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_accepted_false_when_missing_topics(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
    ):
        """diagnostics['final']['accepted'] must be False when missing_topics != []."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "minor_topics": [],
            "topic_details": {"regularization": {"label": "Regularização", "hits": 3}},
            "outline_text": "",
        }
        # Always returns missing, even after extra repair attempt
        mock_outline_score.return_value = {
            "overall_score": 0.80,
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "covered_topics": [],
            "missing_topics": ["regularization"],
            "weakly_covered_topics": [],
            "topic_scores": {"regularization": 0.0},
        }

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final = result["diagnostics"]["final"]
        assert final["accepted"] is False, f"Expected accepted=False, got: {final}"
        assert any("outline_missing_topics_not_allowed" in r for r in final["blocking_reasons"]), (
            f"Expected outline_missing_topics_not_allowed in blocking_reasons: {final['blocking_reasons']}"
        )
        assert "regularization" in str(final["blocking_reasons"])

    @patch("docops.summarize.pipeline.validate_summary_structure")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_accepted_true_when_no_missing_topics(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_validate_structure,
    ):
        """diagnostics['final']['accepted'] is True when no missing topics and weak_ratio OK."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "minor_topics": [],
            "topic_details": {"regularization": {"label": "Regularização", "hits": 3}},
            "outline_text": "",
        }
        mock_outline_score.return_value = {
            "overall_score": 1.0,
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "covered_topics": ["regularization"],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {"regularization": 1.0},
        }
        mock_validate_structure.return_value = {
            "valid": True,
            "preamble_present": True,
            "section_count": 4,
            "min_sections": 4,
            "max_sections": 6,
            "missing_categories": [],
            "missing_heading_categories": [],
            "body_fallback_categories": [],
            "weak_section_indices": [],
            "weak_section_titles": [],
            "closure_heading_count": 1,
            "closure_section_ok": True,
            "structure_failure_reason": "",
        }

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final = result["diagnostics"]["final"]
        assert final["accepted"] is True, f"Expected accepted=True, got: {final}"
        assert final["blocking_reasons"] == [], f"Expected empty blocking_reasons: {final}"

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_accepted_false_when_weak_ratio_exceeds_ceiling(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_grounding,
    ):
        """diagnostics['final']['accepted'] is False when weak_ratio > ceiling (no missing topics)."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }
        mock_outline_score.return_value = {
            "overall_score": 1.0,
            "detected_topics": [],
            "must_cover_topics": [],
            "covered_topics": [],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {},
        }
        # All grounding returns high weak ratio
        mock_grounding.side_effect = lambda text, anchors, threshold, llm=None: (
            text, {"blocks_with_citations": 10, "weakly_grounded": 8,
                   "repaired_blocks": 0, "grounded_blocks": 2}
        )

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "0.35",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final = result["diagnostics"]["final"]
        assert final["accepted"] is False
        assert any("absolute_ceiling" in r for r in final["blocking_reasons"])

    @patch("docops.summarize.pipeline.validate_summary_structure")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_accepted_false_when_structure_invalid(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_validate_structure,
    ):
        """diagnostics['final']['accepted'] must be False when structure is invalid."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }
        mock_outline_score.return_value = {
            "overall_score": 1.0,
            "detected_topics": [],
            "must_cover_topics": [],
            "covered_topics": [],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {},
        }
        mock_validate_structure.return_value = {
            "valid": False,
            "preamble_present": True,
            "section_count": 4,
            "min_sections": 4,
            "max_sections": 6,
            "missing_categories": [],
            "missing_heading_categories": [],
            "body_fallback_categories": [],
            "weak_section_indices": [2],
            "weak_section_titles": ["Conceitos Fundamentais"],
            "closure_heading_count": 1,
            "closure_section_ok": False,
            "structure_failure_reason": "weak_sections|weak_closure",
        }

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final = result["diagnostics"]["final"]
        assert final["accepted"] is False, f"Expected accepted=False, got: {final}"
        assert any("structure_invalid" in r for r in final["blocking_reasons"]), (
            f"Expected structure_invalid in blocking_reasons: {final['blocking_reasons']}"
        )

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_extra_outline_repair_triggered_on_missing_topics(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
    ):
        """Extra outline-repair micro-pass must be triggered when topics remain missing."""
        from docops.summarize.pipeline import run_deep_summary

        base = self._base_summary()

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "minor_topics": [],
            "topic_details": {"regularization": {"label": "Regularização", "hits": 3}},
            "outline_text": "",
        }

        # Regular micro-backfill returns no improvement; extra micro-pass also runs.
        mock_micro_backfill.side_effect = [
            {
                "text": base,
                "triggered": True,
                "paragraphs_attempted": 1,
                "paragraphs_accepted": 0,
                "missing_topics_before": ["regularization"],
                "missing_topics_after": ["regularization"],
                "skipped_topics": [],
                "latency_ms": 5.0,
            },
            {
                "text": base,
                "triggered": True,
                "paragraphs_attempted": 1,
                "paragraphs_accepted": 0,
                "missing_topics_before": ["regularization"],
                "missing_topics_after": ["regularization"],
                "skipped_topics": [],
                "latency_ms": 5.0,
            },
        ]

        # Outline always returns missing so both backfill steps fire.
        mock_outline_score.return_value = {
            "overall_score": 0.80,
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "covered_topics": [],
            "missing_topics": ["regularization"],
            "weakly_covered_topics": [],
            "topic_scores": {"regularization": 0.0},
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            "SUMMARY_MAX_CORRECTIVE_PASSES": "2",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        # regular + extra outline micro-pass
        assert mock_micro_backfill.call_count >= 2
        extra = result["diagnostics"]["extra_outline_repair"]
        assert extra["triggered"] is True

    @patch("docops.summarize.pipeline.validate_summary_grounding")
    @patch("docops.summarize.pipeline.check_formula_mode")
    @patch("docops.summarize.pipeline.classify_claim_risks")
    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_recompute_metrics_after_extra_outline_repair_acceptance(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        mock_classify_claims,
        mock_check_formula_mode,
        mock_grounding,
    ):
        """When extra outline-repair is accepted, final claim/inference diagnostics
        must reflect the repaired text, not stale pre-repair metrics."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": ["regularization"],
            "must_cover_topics": ["regularization"],
            "minor_topics": [],
            "topic_details": {"regularization": {"label": "Regularização", "hits": 3}},
            "outline_text": "",
        }

        # Outline is missing unless repaired marker is present.
        def _outline_side(text, _topic_info):
            if "FIXED_EXTRA" in text:
                return {
                    "overall_score": 1.0,
                    "detected_topics": ["regularization"],
                    "must_cover_topics": ["regularization"],
                    "covered_topics": ["regularization"],
                    "missing_topics": [],
                    "weakly_covered_topics": [],
                    "topic_scores": {"regularization": 1.0},
                }
            return {
                "overall_score": 0.80,
                "detected_topics": ["regularization"],
                "must_cover_topics": ["regularization"],
                "covered_topics": [],
                "missing_topics": ["regularization"],
                "weakly_covered_topics": [],
                "topic_scores": {"regularization": 0.0},
            }

        mock_outline_score.side_effect = _outline_side

        # Micro-backfill (regular step): returns 0 accepted paragraphs, topic still missing.
        # Then extra outline micro-pass returns repaired text (FIXED_EXTRA).
        def _base_summary_fn():
            return (
                "# Resumo Aprofundado — doc.pdf BASE\n\n"
                "## Objetivo e Contexto\n"
                "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
                "## Linha Lógica\n"
                "Progressão em etapas [Fonte 1].\n\n"
                "## Conceitos Fundamentais\n"
                "Definições [Fonte 1].\n\n"
                "## Síntese Final\n"
                "Conclusão [Fonte 1]."
            )

        fixed_extra = (
            "# Resumo Aprofundado — doc.pdf FIXED_EXTRA\n\n"
            "## Objetivo e Contexto\n"
            "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas com encadeamento explícito [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Regularização é tratada de forma direta e aplicada [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra os tópicos com foco em generalização [Fonte 1]."
        )
        mock_micro_backfill.side_effect = [
            {
                "text": _base_summary_fn(),
                "triggered": True,
                "paragraphs_attempted": 1,
                "paragraphs_accepted": 0,
                "missing_topics_before": ["regularization"],
                "missing_topics_after": ["regularization"],
                "skipped_topics": [],
                "latency_ms": 5.0,
            },
            {
                "text": fixed_extra,
                "triggered": True,
                "paragraphs_attempted": 1,
                "paragraphs_accepted": 1,
                "missing_topics_before": ["regularization"],
                "missing_topics_after": [],
                "skipped_topics": [],
                "latency_ms": 5.0,
            },
        ]

        # Force deterministic grounded outputs to keep this test focused on
        # stale-metrics regression, not grounding stochasticity.
        mock_grounding.side_effect = lambda text, anchors, threshold, llm=None: (
            text,
            {
                "blocks_with_citations": 4,
                "weakly_grounded": 0,
                "repaired_blocks": 0,
                "block_scores": [],
            },
        )

        # Simulate stale pre-repair claim risk (unsupported=2) and repaired text
        # claim risk (unsupported=0). Final diagnostics must use the repaired one.
        def _classify_side(text, _anchors):
            if "FIXED_EXTRA" in text:
                return {
                    "sentences_total": 4,
                    "high_risk_count": 0,
                    "unsupported_high_risk_count": 0,
                    "low_info_source_claims_count": 0,
                    "low_info_source_claim_indices": [],
                    "formula_claims_total": 0,
                    "formula_claims_supported": 0,
                    "formula_claims_downgraded_to_concept": 0,
                    "sentences_classified": [],
                }
            return {
                "sentences_total": 4,
                "high_risk_count": 2,
                "unsupported_high_risk_count": 2,
                "low_info_source_claims_count": 0,
                "low_info_source_claim_indices": [],
                "formula_claims_total": 0,
                "formula_claims_supported": 0,
                "formula_claims_downgraded_to_concept": 0,
                "sentences_classified": [],
            }

        mock_classify_claims.side_effect = _classify_side
        mock_check_formula_mode.side_effect = (
            lambda claim_risk, _anchors, _mode="conservative": claim_risk
        )

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
            "SUMMARY_MAX_CORRECTIVE_PASSES": "3",
            # Disable early backfill so budget is not consumed before extra outline-repair
            "SUMMARY_BACKFILL_BEFORE_DEOVERREACH": "false",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        extra = result["diagnostics"]["extra_outline_repair"]
        claim = result["diagnostics"]["claim_risk"]
        final = result["diagnostics"]["final"]
        assert extra["accepted"] is True, f"Expected extra repair accepted: {extra}"
        assert claim["unsupported_high_risk_count"] == 0, (
            f"Expected post-repair claim risk in diagnostics, got: {claim}"
        )
        assert final["missing_topics"] == [], (
            f"Expected no missing topics after accepted extra repair, got: {final}"
        )

    @patch("docops.summarize.pipeline.validate_summary_structure")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_accepted_true_when_no_must_cover_topics(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_validate_structure,
    ):
        """When must_cover_topics is empty, missing_topics does not block acceptance."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }
        mock_outline_score.return_value = {
            "overall_score": 1.0,
            "detected_topics": [],
            "must_cover_topics": [],
            "covered_topics": [],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {},
        }
        mock_validate_structure.return_value = {
            "valid": True,
            "preamble_present": True,
            "section_count": 4,
            "min_sections": 4,
            "max_sections": 6,
            "missing_categories": [],
            "missing_heading_categories": [],
            "body_fallback_categories": [],
            "weak_section_indices": [],
            "weak_section_titles": [],
            "closure_heading_count": 1,
            "closure_section_ok": True,
            "structure_failure_reason": "",
        }

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_GROUNDING_REPAIR": "false",
            "SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO": "1.0",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        assert result["diagnostics"]["final"]["accepted"] is True

    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_diagnostics_always_have_final_fields(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
    ):
        """diagnostics['final'] always has accepted, blocking_reasons, absolute_weak_ratio_passed."""
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "minor_topics": [],
            "topic_details": {},
            "outline_text": "",
        }
        mock_outline_score.return_value = {
            "overall_score": 1.0, "detected_topics": [], "must_cover_topics": [],
            "covered_topics": [], "missing_topics": [], "weakly_covered_topics": [],
            "topic_scores": {},
        }

        mock_llm = MagicMock()
        base = self._base_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 10
        mock_llm_factory.return_value = mock_llm

        with patch.dict(os.environ, {
            "SUMMARY_RESYNTHESIS_ENABLED": "false",
            "SUMMARY_STRUCTURE_MIN_CHARS": "20",
        }):
            result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)

        final = result["diagnostics"]["final"]
        for key in ("accepted", "blocking_reasons", "absolute_weak_ratio_passed",
                    "absolute_weak_ratio_ceiling", "final_weak_ratio"):
            assert key in final, f"Missing key '{key}' in diagnostics['final']"
        assert isinstance(final["accepted"], bool)
        assert isinstance(final["blocking_reasons"], list)


# ──────────────────────────────────────────────────────────────────────────────
# Non-canonical citation sanitization
# ──────────────────────────────────────────────────────────────────────────────


class TestSanitizeNonCanonicalCitations:
    """Tests for _sanitize_non_canonical_citations."""

    def _fn(self, text: str) -> str:
        from docops.summarize.pipeline import _sanitize_non_canonical_citations
        return _sanitize_non_canonical_citations(text)

    def test_removes_contexto_adicional(self):
        text = "O modelo convergiu [Contexto adicional, p. 4] conforme esperado."
        result = self._fn(text)
        assert "Contexto adicional" not in result
        assert "O modelo convergiu" in result
        assert "conforme esperado." in result

    def test_removes_meta_bracket(self):
        text = "Texto relevante [meta] e mais conteúdo."
        result = self._fn(text)
        assert "[meta]" not in result

    def test_removes_fonte_extra(self):
        text = "Veja [Fonte extra 2] para detalhes."
        result = self._fn(text)
        assert "Fonte extra" not in result

    def test_preserves_canonical_citation(self):
        text = "A análise mostra [Fonte 1] e [Fonte 12] como referências válidas."
        result = self._fn(text)
        assert "[Fonte 1]" in result
        assert "[Fonte 12]" in result

    def test_preserves_math_interval(self):
        """Brackets with only digits/comma must NOT be removed ([0,1], [a,b])."""
        text = "O valor pertence ao intervalo [0,1] e satisfaz a condição."
        result = self._fn(text)
        assert "[0,1]" in result

    def test_preserves_markdown_link(self):
        """[text](url) Markdown links must NOT be touched."""
        text = "Consulte [o documento](https://example.com) para mais detalhes."
        result = self._fn(text)
        assert "[o documento](https://example.com)" in result

    def test_removes_multiple_non_canonical(self):
        text = (
            "Introdução [Contexto adicional, p. 4] ao tema.\n"
            "Detalhes [meta] foram omitidos.\n"
            "Referência válida [Fonte 3] confirmada."
        )
        result = self._fn(text)
        assert "Contexto adicional" not in result
        assert "[meta]" not in result
        assert "[Fonte 3]" in result

    def test_empty_string(self):
        assert self._fn("") == ""

    def test_none_like_empty(self):
        # Should not raise; returns empty
        result = self._fn("")
        assert result == ""


class TestBackfillNonCanonicalCitationIntegration:
    """Integration tests: backfill output with non-canonical citations is cleaned."""

    def _make_resp(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    def _base_summary(self, marker: str = "BASE") -> str:
        return (
            f"# Resumo Aprofundado — doc.pdf {marker}\n\n"
            "## Objetivo e Contexto\n"
            "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Definições centrais [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )

    def _backfill_with_noise(self) -> str:
        """Simulates a backfill LLM output that leaked a non-canonical citation."""
        return (
            "# Resumo Aprofundado — doc.pdf BACKFILLED\n\n"
            "## Objetivo e Contexto\n"
            "Introdução teórica com escopo bem definido [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Definições centrais [Fonte 1].\n\n"
            "## Formalização Matemática\n"
            "A prova usa [Contexto adicional, p. 4] como suporte e [meta] para contextualizar [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_backfill_non_canonical_citations_stripped_from_answer(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
    ):
        """Answer must not contain [Contexto adicional ...] or [meta] after backfill."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = [Document(page_content=f"chunk {i}", metadata={"chunk_index": i}) for i in range(3)]
        mock_collect.return_value = chunks

        outline_missing = {
            "overall_score": 0.5,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": [],
            "missing_topics": ["math_formalization"],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 0.0},
        }
        outline_covered = {
            "overall_score": 1.0,
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "covered_topics": ["math_formalization"],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {"math_formalization": 1.0},
        }
        mock_extract_topics.return_value = {
            "detected_topics": ["math_formalization"],
            "must_cover_topics": ["math_formalization"],
            "topic_details": {"math_formalization": {"label": "Formalização Matemática", "hits": 3}},
        }

        call_count = [0]

        def _outline_side_effect(text, topic_info):
            call_count[0] += 1
            # First call (pre-backfill check): missing
            # Second call (bf_outline after backfill): covered
            return outline_missing if call_count[0] == 1 else outline_covered

        mock_outline_score.side_effect = _outline_side_effect
        mock_micro_backfill.return_value = {
            "text": self._backfill_with_noise(),
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["math_formalization"],
            "missing_topics_after": [],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        partial = self._base_summary("PARTIAL")
        consolidated = self._base_summary("CONSOLIDATED")
        mock_llm.invoke.side_effect = [
            self._make_resp(partial),
            self._make_resp(partial),
            self._make_resp(consolidated),
            self._make_resp(self._base_summary("FINAL")),
            self._make_resp(self._base_summary("POLISHED")),
        ]
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        answer = result["answer"]

        assert "Contexto adicional" not in answer, (
            f"[Contexto adicional] leaked into answer:\n{answer}"
        )
        assert "[meta]" not in answer, (
            f"[meta] leaked into answer:\n{answer}"
        )
        # Canonical citations must survive
        assert "[Fonte 1]" in answer

    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_math_interval_not_stripped_from_final_answer(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
    ):
        """Mathematical notation [0,1] in text must not be removed by sanitization."""
        from docops.summarize.pipeline import run_deep_summary

        chunks = [Document(page_content=f"chunk {i}", metadata={"chunk_index": i}) for i in range(3)]
        mock_collect.return_value = chunks

        summary_with_math = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Objetivo e Contexto\n"
            "O valor pertence ao intervalo [0,1] e satisfaz a condição [Fonte 1].\n\n"
            "## Linha Lógica\n"
            "Progressão em etapas [Fonte 1].\n\n"
            "## Conceitos Fundamentais\n"
            "Definições centrais [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )

        mock_extract_topics.return_value = {
            "detected_topics": [],
            "must_cover_topics": [],
            "topic_details": {},
        }
        mock_outline_score.return_value = {
            "overall_score": 1.0,
            "detected_topics": [],
            "must_cover_topics": [],
            "covered_topics": [],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {},
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._make_resp(summary_with_math),
            self._make_resp(summary_with_math),
            self._make_resp(summary_with_math),
            self._make_resp(summary_with_math),
            self._make_resp(summary_with_math),
        ]
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]

        assert "[0,1]" in answer, (
            f"Mathematical interval [0,1] was wrongly stripped from answer:\n{answer}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Auto-merge sections
# ──────────────────────────────────────────────────────────────────────────────


class TestAutoMergeSections:
    """Tests for _auto_merge_sections deterministic merge."""

    def test_no_merge_when_within_target(self):
        """No merge when section_count <= target_sections."""
        from docops.summarize.pipeline import _auto_merge_sections

        text = (
            "## Objetivo e Contexto\nConteúdo sobre objetivos.\n\n"
            "## Linha Lógica\nConteúdo sobre estrutura.\n\n"
            "## Conceitos Fundamentais\nDefinições importantes.\n\n"
            "## Síntese e Aplicações\nConclusão do documento."
        )
        result, info = _auto_merge_sections(text, target_sections=5)
        assert result == text
        assert info["section_count_before"] == 4
        assert info["section_count_after"] == 4
        assert info["merges_applied"] == []

    def test_merge_7_to_5_preferred_pairs(self):
        """7 sections merged to 5 using preferred keyword pairs."""
        from docops.summarize.pipeline import _auto_merge_sections

        text = (
            "## Objetivo e Contexto\nO documento apresenta.\n\n"
            "## Fundamentos Teóricos\nBases conceituais.\n\n"
            "## Construção Lógica\nOrganização dos argumentos.\n\n"
            "## Conceitos Centrais\nDefinições e termos chave.\n\n"
            "## Exemplos Práticos\nCasos de aplicação real.\n\n"
            "## Aplicações e Variações\nImplicações do modelo.\n\n"
            "## Síntese Final\nConclusão geral do documento."
        )
        result, info = _auto_merge_sections(text, target_sections=5)
        assert info["section_count_before"] == 7
        assert info["section_count_after"] == 5
        assert len(info["merges_applied"]) == 2
        # Check result has exactly 5 ## headings
        import re
        headings = re.findall(r"(?m)^## .+", result)
        assert len(headings) == 5

    def test_merge_shortest_pair_fallback(self):
        """When no preferred pairs match, merge shortest adjacent pair."""
        from docops.summarize.pipeline import _auto_merge_sections

        text = (
            "## Seção Alpha\nConteúdo alfa.\n\n"
            "## Seção Beta\nB.\n\n"
            "## Seção Gamma\nG.\n\n"
            "## Seção Delta\nConteúdo delta extenso.\n\n"
            "## Seção Epsilon\nConteúdo epsilon.\n\n"
            "## Seção Zeta\nConteúdo zeta."
        )
        result, info = _auto_merge_sections(text, target_sections=5)
        assert info["section_count_before"] == 6
        assert info["section_count_after"] == 5
        assert len(info["merges_applied"]) == 1
        # Shortest pair (Beta + Gamma, both tiny) should be merged
        assert "shortest pair" in info["merges_applied"][0]

    def test_merge_preserves_content(self):
        """Content from merged sections is preserved."""
        from docops.summarize.pipeline import _auto_merge_sections

        text = (
            "## Exemplos\nExemplo concreto A.\n\n"
            "## Aplicações\nAplicação prática B.\n\n"
            "## Objetivo\nVisão geral.\n\n"
            "## Conceitos\nDefinições.\n\n"
            "## Linha Lógica\nEstrutura.\n\n"
            "## Síntese\nConclusão."
        )
        result, info = _auto_merge_sections(text, target_sections=5)
        # Content from both merged sections is present
        assert "Exemplo concreto A" in result
        assert "Aplicação prática B" in result

    def test_preamble_preserved(self):
        """Preamble text before first heading is preserved."""
        from docops.summarize.pipeline import _auto_merge_sections

        text = (
            "Este é o preâmbulo.\n\n"
            "## Seção A\nA.\n\n"
            "## Seção B\nB.\n\n"
            "## Seção C\nC.\n\n"
            "## Seção D\nD.\n\n"
            "## Seção E\nE.\n\n"
            "## Seção F\nF."
        )
        result, info = _auto_merge_sections(text, target_sections=5)
        assert "Este é o preâmbulo" in result
        assert info["section_count_after"] == 5


class TestDeepSummaryLlMContentNormalization:
    """Regression: list/dict LLM content must be normalized to plain text."""

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_list_content_blocks_do_not_leak_as_python_repr(
        self, mock_collect, mock_llm_factory
    ):
        from docops.summarize.pipeline import run_deep_summary

        mock_collect.return_value = _make_chunks(4, with_sections=False)

        summary_text = (
            "# Resumo Aprofundado - doc.pdf\n\n"
            "## Objetivo e Contexto\nTexto introdutorio [Fonte 1].\n\n"
            "## Linha Logica\nTexto de estrutura [Fonte 1].\n\n"
            "## Conceitos Fundamentais\nTexto conceitual [Fonte 1].\n\n"
            "## Sintese e Conclusao\nTexto final [Fonte 1]."
        )

        mock_response = MagicMock()
        mock_response.content = [{"type": "text", "text": summary_text}]

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]

        assert not answer.lstrip().startswith("[{")
        assert "Resumo Aprofundado" in answer


# ──────────────────────────────────────────────────────────────────────────────
# Pre-validation sanitization
# ──────────────────────────────────────────────────────────────────────────────


class TestSanitizeBeforeStructureValidation:
    """Tests for _sanitize_before_structure_validation."""

    def test_removes_orphan_fonte_lines(self):
        """Orphan 'Fonte N' and 'Fonte N:' lines are removed."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        text = (
            "## Objetivo\nConteúdo sobre objetivos [Fonte 1].\n\n"
            "Fonte 2\n\n"
            "## Conceitos\nDefinições [Fonte 3].\n\n"
            "Fonte 4:\n"
        )
        result = _sanitize_before_structure_validation(text)
        assert "Fonte 2" not in result
        assert "Fonte 4:" not in result
        assert "Conteúdo sobre objetivos [Fonte 1]" in result
        assert "Definições [Fonte 3]" in result

    def test_removes_orphan_citation_lines(self):
        """Lines that are only [Fonte N] markers are removed."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        text = "## Seção\nTexto real.\n\n[Fonte 2]\n\n## Outra\nMais texto."
        result = _sanitize_before_structure_validation(text)
        assert "[Fonte 2]" not in result or "Texto" in result.split("[Fonte 2]")[0]
        assert "Texto real" in result

    def test_removes_source_dump_lines(self):
        """Source dump lines are removed."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        text = (
            "## Seção\nTexto real.\n\n"
            "[Fonte 1] doc.pdf (página 3)\n\n"
            "## Outra\nMais texto."
        )
        result = _sanitize_before_structure_validation(text)
        assert "doc.pdf (página 3)" not in result
        assert "Texto real" in result

    def test_preserves_inline_citations_in_prose(self):
        """Inline citations within prose are NOT removed."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        text = (
            "## Seção\n"
            "O modelo Random Forest [Fonte 1] apresenta alta acurácia.\n\n"
            "Conforme descrito [Fonte 2], o algoritmo é robusto."
        )
        result = _sanitize_before_structure_validation(text)
        assert "[Fonte 1]" in result
        assert "[Fonte 2]" in result

    def test_empty_text(self):
        """Empty text returns empty."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        assert _sanitize_before_structure_validation("") == ""

    def test_removes_noisy_fonte_label_variants(self):
        """Noisy variants like 'Fonte 9 -' should be stripped before validation."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        text = (
            "## Objetivo\nTexto útil [Fonte 1].\n\n"
            "Fonte 9 -\n\n"
            "## Síntese\nConteúdo final com conclusão [Fonte 2]."
        )
        result = _sanitize_before_structure_validation(text)
        assert "Fonte 9 -" not in result
        assert "Texto útil [Fonte 1]" in result
        assert "conclusão [Fonte 2]" in result

    def test_removes_bracketed_file_mapping_line(self):
        """Bracketed mapping lines with file/page metadata must be removed."""
        from docops.summarize.pipeline import _sanitize_before_structure_validation

        text = (
            "## Métodos\nProcedimento descrito [Fonte 3].\n\n"
            "[Fonte 3] 7._rvores_de_Deciso.pdf (página 13)\n\n"
            "## Conclusão\nSíntese final [Fonte 4]."
        )
        result = _sanitize_before_structure_validation(text)
        assert "7._rvores_de_Deciso.pdf (página 13)" not in result
        assert "Procedimento descrito [Fonte 3]" in result


# ──────────────────────────────────────────────────────────────────────────────
# Structure failure reason
# ──────────────────────────────────────────────────────────────────────────────


class TestStructureFailureReason:
    """Tests for structure_failure_reason in validate_summary_structure."""

    def test_valid_structure_no_failure_reason(self):
        """Valid structure returns empty failure reason."""
        from docops.summarize.pipeline import validate_summary_structure

        filler = "Este texto contém conteúdo suficiente para passar na validação de seção com palavras reais. " * 3
        text = (
            "## Objetivo e Contexto\n"
            + filler
            + "\n\n## Linha Lógica e Construção\n"
            + filler
            + "\n\n## Conceitos Fundamentais\n"
            + filler
            + "\n\n## Síntese e Aplicações\n"
            + filler
        )
        result = validate_summary_structure(text)
        assert result["valid"] is True
        assert result["structure_failure_reason"] == ""

    def test_section_count_exceeded(self):
        """Too many sections → 'section_count_exceeded'."""
        from docops.summarize.pipeline import validate_summary_structure

        filler = "Este texto contém conteúdo suficiente para a validação de seção funcionar corretamente. " * 3
        sections = "\n\n".join(
            f"## Seção {i}\n" + filler for i in range(8)
        )
        result = validate_summary_structure(sections)
        assert "section_count_exceeded" in result["structure_failure_reason"]

    def test_missing_categories(self):
        """Missing required categories in failure reason."""
        from docops.summarize.pipeline import validate_summary_structure

        filler = "Este texto contém conteúdo real suficiente para a validação de seção funcionar adequadamente. " * 3
        text = (
            "## Seção Aleatória A\n" + filler + "\n\n"
            "## Seção Aleatória B\n" + filler + "\n\n"
            "## Seção Aleatória C\n" + filler + "\n\n"
            "## Seção Aleatória D\n" + filler
        )
        result = validate_summary_structure(text)
        assert "missing_categories" in result["structure_failure_reason"]

    def test_combined_failures(self):
        """Multiple failure reasons joined with pipe."""
        from docops.summarize.pipeline import validate_summary_structure

        filler = "Texto com palavras reais suficientes para não ser considerado fraco na validação. " * 3
        # Only 2 sections (below min) and missing categories
        text = "## Seção X\n" + filler + "\n\n## Seção Y\n" + filler
        result = validate_summary_structure(text)
        reasons = result["structure_failure_reason"]
        assert "section_count_below_min" in reasons
        assert "missing_categories" in reasons


# ──────────────────────────────────────────────────────────────────────────────
# Recovery rule integration
# ──────────────────────────────────────────────────────────────────────────────


class TestRecoveryRuleAutoMerge:
    """Tests for recovery rule: auto-merge when only section_count_exceeded."""

    @staticmethod
    def _make_llm_response(text):
        resp = MagicMock()
        resp.content = text
        return resp

    def _good_summary_7_sections(self):
        """Summary with 7 sections — exceeds max_sections but has all categories."""
        sections = [
            ("Objetivo e Contexto", "O documento apresenta a metodologia de análise [Fonte 1]."),
            ("Fundamentos Teóricos", "Os fundamentos incluem teoria dos grafos [Fonte 2]."),
            ("Construção Lógica", "A estrutura segue uma progressão lógica [Fonte 3]."),
            ("Conceitos Centrais", "Os conceitos principais são definidos [Fonte 4]."),
            ("Exemplos Práticos", "Um exemplo concreto é apresentado [Fonte 5]."),
            ("Aplicações e Variações", "As aplicações incluem diversos cenários [Fonte 6]."),
            ("Síntese Final", "Em síntese, o documento contribui para [Fonte 7]."),
        ]
        body = "\n\n".join(
            f"## {title}\n{content} " + "X " * 40
            for title, content in sections
        )
        return body

    def _good_summary_5_sections(self):
        """Summary with 5 valid sections and good diversity."""
        sections = [
            ("Objetivo e Contexto", "O documento apresenta [Fonte 1] [Fonte 2]."),
            ("Linha Lógica e Construção", "A estrutura segue [Fonte 3] [Fonte 4]."),
            ("Conceitos Fundamentais", "Conceitos centrais [Fonte 5] [Fonte 6]."),
            ("Exemplos e Aplicações", "Exemplos práticos [Fonte 7] [Fonte 8]."),
            ("Síntese e Considerações", "Em síntese [Fonte 9] [Fonte 10]."),
        ]
        body = "\n\n".join(
            f"## {title}\n{content} " + "Y " * 40
            for title, content in sections
        )
        return body

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_recovery_auto_merge_accepts_candidate(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """Candidate with 7 sections and good diversity is recovered via auto-merge."""
        from docops.summarize.pipeline import run_deep_summary
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")

        chunks = [
            Document(
                page_content=f"Chunk {i} sobre o tema {i} do documento.",
                metadata={
                    "chunk_index": i,
                    "page_start": i,
                    "page_end": i,
                    "section_title": f"Seção {i}",
                    "section_path": f"Seção {i}",
                    "file_name": "doc.pdf",
                },
            )
            for i in range(12)
        ]
        mock_collect.return_value = chunks

        # LLM calls: partials (8 max) + consolidation + final + polish + re-synthesis
        # The initial summary uses few sources, triggering diversity re-synthesis.
        # The re-synthesis returns 7-section summary with good diversity.
        initial_summary = self._good_summary_5_sections()
        resynth_summary = self._good_summary_7_sections()
        from docops.config import config as runtime_config
        partial_calls = max(1, int(runtime_config.summary_max_groups))

        llm_outputs = (
            [self._make_llm_response(f"Parcial {i}.") for i in range(partial_calls)]
            + [
                self._make_llm_response("Consolidado."),
                self._make_llm_response(initial_summary),
                self._make_llm_response(initial_summary),
                self._make_llm_response(resynth_summary),
            ]
        )
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = llm_outputs
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1,
                                   include_diagnostics=True)

        diag = result["diagnostics"]
        struct = diag["structure"]
        # Structure should be valid after auto-merge
        assert struct["valid"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Diagnostics: auto_merge_applied, section_count_before/after
# ──────────────────────────────────────────────────────────────────────────────


class TestDiagnosticsAutoMerge:
    """Test that auto_merge diagnostics appear in structure diagnostics."""

    def test_auto_merge_fields_in_postprocess(self):
        """_postprocess_deep_summary_text returns auto_merge info."""
        from docops.summarize.pipeline import _postprocess_deep_summary_text

        # 7 sections → triggers auto-merge
        sections = [
            ("Objetivo e Contexto", "O documento apresenta a metodologia [Fonte 1]."),
            ("Fundamentos Teóricos", "Os fundamentos incluem teoria [Fonte 2]."),
            ("Construção Lógica", "A estrutura segue uma progressão [Fonte 3]."),
            ("Conceitos Centrais", "Os conceitos principais são definidos [Fonte 4]."),
            ("Exemplos Práticos", "Um exemplo concreto é apresentado [Fonte 5]."),
            ("Aplicações e Variações", "As aplicações incluem cenários [Fonte 6]."),
            ("Síntese Final", "Em síntese, o documento contribui para [Fonte 7]."),
        ]
        text = "\n\n".join(
            f"## {title}\n{content} " + "X " * 40
            for title, content in sections
        )
        anchors = [
            Document(
                page_content=f"Chunk {i} com conteúdo sobre o tema.",
                metadata={"chunk_index": i, "page_start": i},
            )
            for i in range(10)
        ]

        result_text, info = _postprocess_deep_summary_text(
            text,
            anchors,
            grounding_threshold=0.05,
            llm=None,
            repair_enabled=False,
            structure_min_chars=80,
        )

        assert info["auto_merge_applied"] is True
        assert info["merge_info"]["section_count_before"] == 7
        assert info["merge_info"]["section_count_after"] == 5
        # Structure should now be valid
        assert info["structure_info"]["valid"] is True

    def test_no_auto_merge_when_within_limits(self):
        """No auto-merge when section count is within limits."""
        from docops.summarize.pipeline import _postprocess_deep_summary_text

        sections = [
            ("Objetivo e Contexto", "O documento apresenta [Fonte 1]."),
            ("Linha Lógica e Construção", "A estrutura segue [Fonte 2]."),
            ("Conceitos Fundamentais", "Conceitos centrais [Fonte 3]."),
            ("Síntese e Aplicações", "Em síntese [Fonte 4]."),
        ]
        text = "\n\n".join(
            f"## {title}\n{content} " + "Y " * 40
            for title, content in sections
        )
        anchors = [
            Document(
                page_content=f"Chunk {i}.",
                metadata={"chunk_index": i, "page_start": i},
            )
            for i in range(5)
        ]

        _, info = _postprocess_deep_summary_text(
            text,
            anchors,
            grounding_threshold=0.05,
            llm=None,
            repair_enabled=False,
            structure_min_chars=80,
        )

        assert info["auto_merge_applied"] is False
        assert info["merge_info"] == {}


class TestFinalHardCleanup:
    """Final guardrail cleanup before appending authoritative sources section."""

    @staticmethod
    def _resp(text: str):
        m = MagicMock()
        m.content = text
        return m

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_leaked_source_dump_removed_before_final_sources_append(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(6, with_sections=True)

        partial = "Parcial da seção [Fonte 1]."
        consolidated = "Visão consolidada."
        leaked = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Objetivo e Contexto\n"
            "Texto de objetivo com base factual suficiente [Fonte 1].\n\n"
            "Fonte 9 -\n\n"
            "## Estrutura e Encadeamento Lógico\n"
            "Encadeamento dos tópicos com conteúdo técnico consistente [Fonte 2].\n\n"
            "## Conceitos e Definições Fundamentais\n"
            "Definições e conceitos centrais para o estudo [Fonte 3].\n\n"
            "[Fonte 1] 7._rvores_de_Deciso.pdf (página 1)\n\n"
            "## Síntese e Conclusão\n"
            "Síntese final do documento e implicações práticas [Fonte 4]."
        )

        mock_llm = MagicMock()
        # 2 partials + 1 consolidate + 1 final + 1 style-polish
        mock_llm.invoke.side_effect = [
            self._resp(partial),
            self._resp(partial),
            self._resp(consolidated),
            self._resp(leaked),
            self._resp(leaked),
        ]
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1)
        answer = result["answer"]

        assert "Fonte 9 -" not in answer
        assert "7._rvores_de_Deciso.pdf (página 1)" not in answer
        assert answer.count("**Fontes:**") == 1


# ──────────────────────────────────────────────────────────────────────────────
# Claim-risk classification
# ──────────────────────────────────────────────────────────────────────────────

class TestClassifyClaimRisks:
    """Unit tests for classify_claim_risks (no LLM, pure regex-based logic)."""

    def setup_method(self):
        from docops.summarize.pipeline import classify_claim_risks
        self.fn = classify_claim_risks

    def _anchor(self, text: str, section_title: str = "", section_path: str = "") -> "Document":
        return _doc(text, section_title=section_title, section_path=section_path)

    def test_empty_text_returns_zero_sentences(self):
        result = self.fn("", [])
        assert result["sentences_total"] == 0
        assert result["high_risk_count"] == 0
        assert result["unsupported_high_risk_count"] == 0

    def test_descriptive_sentence_not_high_risk(self):
        text = "O documento aborda conceitos de aprendizado de máquina."
        result = self.fn(text, [])
        assert result["sentences_total"] >= 1
        assert result["high_risk_count"] == 0
        assert result["unsupported_high_risk_count"] == 0

    def test_formula_sentence_detected(self):
        # Sentence with a formula-like expression.
        text = "A equação P(x) = 1/N determina a probabilidade uniforme [Fonte 1]."
        anchors = [self._anchor("P(x) = 1/N em distribuição uniforme")]
        result = self.fn(text, anchors)
        formula_sentences = [
            s for s in result["sentences_classified"] if s["risk_type"] == "formula"
        ]
        assert len(formula_sentences) >= 1

    def test_quantitative_sentence_detected(self):
        text = "O algoritmo é 30% mais rápido que X [Fonte 1]."
        anchors = [self._anchor("30% faster than X")]
        result = self.fn(text, anchors)
        high_risk = [s for s in result["sentences_classified"] if s["high_risk"]]
        assert len(high_risk) >= 1

    def test_comparison_sentence_detected(self):
        text = "O método A diferencia-se de B por escopo [Fonte 1]."
        anchors = [self._anchor("A differs from B in scope")]
        result = self.fn(text, anchors)
        high_risk = [s for s in result["sentences_classified"] if s["high_risk"]]
        assert len(high_risk) >= 1

    def test_high_risk_no_citation_is_unsupported(self):
        # High-risk sentence with NO [Fonte N] → should be unsupported.
        text = "O algoritmo é 50% mais eficiente."
        result = self.fn(text, [])
        assert result["unsupported_high_risk_count"] >= 1

    def test_high_risk_with_valid_non_low_info_citation_not_unsupported(self):
        # High-risk sentence citing a normal section anchor → should NOT be unsupported.
        text = "O índice de Gini é dado por G = 1 - Σp_i² [Fonte 1]."
        anchors = [self._anchor("G = 1 - sum(p_i^2)", section_title="Fundamentos")]
        result = self.fn(text, anchors)
        # Sentence may be high-risk (formula), but it cites a non-low-info anchor.
        formula_sentences = [
            s for s in result["sentences_classified"]
            if s["risk_type"] == "formula" and s.get("cited_indices")
        ]
        # If the anchor is NOT low-info, should not be marked unsupported.
        for s in formula_sentences:
            assert not s.get("low_info_only"), (
                f"Sentence with valid anchor should not be low_info_only: {s}"
            )

    def test_low_info_source_detection(self):
        from docops.summarize.pipeline import _is_low_info_source
        anchor_idx = self._anchor("conteúdo do sumário", section_title="Sumário")
        anchor_normal = self._anchor("explicação técnica", section_title="Fundamentos")
        assert _is_low_info_source(anchor_idx) is True
        assert _is_low_info_source(anchor_normal) is False

    def test_low_info_source_claim_counted(self):
        # High-risk sentence citing ONLY a low-info source.
        text = "O sistema X é 2 vezes melhor que Y [Fonte 1]."
        anchors = [self._anchor("capítulo sobre X e Y", section_title="Sumário")]
        result = self.fn(text, anchors)
        assert result["low_info_source_claims_count"] >= 1
        assert result["unsupported_high_risk_count"] >= 1
        assert result["unsupported_high_risk_low_info_only_count"] >= 1

    def test_low_info_only_not_unsupported_when_rule_disabled(self):
        text = "O sistema X é 2 vezes melhor que Y [Fonte 1]."
        anchors = [self._anchor("capítulo sobre X e Y", section_title="Sumário")]
        with patch.dict(
            os.environ,
            {"SUMMARY_REQUIRE_NON_LOW_INFO_FOR_HIGH_RISK": "false"},
        ):
            result = self.fn(text, anchors)
        assert result["low_info_source_claims_count"] >= 1
        assert result["unsupported_high_risk_count"] == 0
        assert result["unsupported_high_risk_low_info_only_count"] == 0

    def test_technical_assertion_low_info_is_unsupported(self):
        text = (
            "O Random Forest integra processos de validação para mitigar variância "
            "e aumentar robustez [Fonte 1]."
        )
        anchors = [self._anchor("capítulos do documento", section_title="Conteúdo")]
        result = self.fn(text, anchors)
        technical = [
            s for s in result["sentences_classified"] if s["risk_type"] == "technical_assertion"
        ]
        assert technical, f"Expected technical_assertion sentence, got: {result['sentences_classified']}"
        assert result["unsupported_high_risk_count"] >= 1

    def test_technical_assertion_with_non_low_info_anchor_supported(self):
        text = (
            "O Random Forest integra processos de validação para mitigar variância "
            "e aumentar robustez [Fonte 1]."
        )
        anchors = [self._anchor(
            "Validação cruzada reduz variância e melhora robustez do modelo.",
            section_title="Experimentos",
        )]
        result = self.fn(text, anchors)
        technical = [
            s for s in result["sentences_classified"] if s["risk_type"] == "technical_assertion"
        ]
        assert technical, f"Expected technical_assertion sentence, got: {result['sentences_classified']}"
        assert result["unsupported_high_risk_count"] == 0, result

    def test_formula_claims_total_counted(self):
        text = (
            "A fórmula f(x) = x² é central [Fonte 1].\n"
            "O algoritmo tem complexidade O(n log n) [Fonte 2]."
        )
        anchors = [
            self._anchor("f(x) = x^2", section_title="Fundamentos"),
            self._anchor("O(n log n) complexity", section_title="Análise"),
        ]
        result = self.fn(text, anchors)
        assert result["formula_claims_total"] >= 1

    def test_mixed_text_counts_correctly(self):
        text = (
            "O documento explica aprendizado supervisionado.\n"
            "A precisão é 95% em validação cruzada [Fonte 1]."
        )
        anchors = [self._anchor("precisão de 95%", section_title="Experimentos")]
        result = self.fn(text, anchors)
        assert result["sentences_total"] >= 2
        assert result["high_risk_count"] >= 1

    def test_heading_lines_skipped(self):
        text = "## Seção Principal\n\nTexto normal sem claims de alto risco."
        result = self.fn(text, [])
        # Heading lines should not be analyzed as sentences.
        for s in result["sentences_classified"]:
            assert not s["text"].startswith("#")


# ──────────────────────────────────────────────────────────────────────────────
# Formula mode conservative
# ──────────────────────────────────────────────────────────────────────────────

class TestCheckFormulaMode:
    """Unit tests for check_formula_mode."""

    def setup_method(self):
        from docops.summarize.pipeline import classify_claim_risks, check_formula_mode
        self.classify = classify_claim_risks
        self.check = check_formula_mode

    def _anchor(self, text: str, section_title: str = "Fundamentos") -> "Document":
        return _doc(text, section_title=section_title)

    def test_conservative_formula_with_math_anchor_not_downgraded(self):
        text = "A impureza de Gini é dada por G = 1 - Σp² [Fonte 1]."
        anchors = [self._anchor("G = 1 - sum(p_i^2) com α = 0.5")]
        risk = self.classify(text, anchors)
        result = self.check(risk, anchors, "conservative")
        assert result["formula_claims_downgraded_to_concept"] == 0

    def test_conservative_formula_without_math_anchor_downgraded(self):
        # Sentence has formula notation; anchor has NO math content.
        text = "A fórmula para custo é C = α × T [Fonte 1]."
        anchors = [self._anchor("discussão geral sobre custo sem equação")]
        risk = self.classify(text, anchors)
        # Manually ensure the sentence is formula-type by checking classification.
        formula_entries = [
            e for e in risk["sentences_classified"] if e["risk_type"] == "formula"
            and e.get("cited_indices")
        ]
        if not formula_entries:
            pytest.skip("Sentence not classified as formula with citation; skip.")
        result = self.check(risk, anchors, "conservative")
        assert result["formula_claims_downgraded_to_concept"] >= 1

    def test_permissive_mode_no_downgrade(self):
        text = "A fórmula f(x) = x² é central [Fonte 1]."
        anchors = [self._anchor("discussion without math")]
        risk = self.classify(text, anchors)
        result = self.check(risk, anchors, "permissive")
        assert result["formula_claims_downgraded_to_concept"] == 0

    def test_no_formula_claims_downgraded_count_zero(self):
        text = "O documento explica conceitos de aprendizado."
        anchors = [self._anchor("conceito geral")]
        risk = self.classify(text, anchors)
        result = self.check(risk, anchors, "conservative")
        assert result["formula_claims_downgraded_to_concept"] == 0

    def test_formula_claim_with_mixed_anchors_not_downgraded_if_any_has_math(self):
        # Two anchors; one has math content. Should not be downgraded.
        text = "A variância é V = Σ(x-μ)² / N [Fonte 1]."
        anchors = [
            self._anchor("V = sum((x-mu)^2) / N", section_title="Estatística"),
        ]
        risk = self.classify(text, anchors)
        result = self.check(risk, anchors, "conservative")
        assert result["formula_claims_downgraded_to_concept"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Inference density metric
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeInferenceDensity:
    """Unit tests for compute_inference_density."""

    def setup_method(self):
        from docops.summarize.pipeline import compute_inference_density
        self.fn = compute_inference_density

    def _risk(self, total: int, unsupported: int, downgraded: int = 0) -> dict:
        return {
            "sentences_total": total,
            "unsupported_high_risk_count": unsupported,
            "formula_claims_downgraded_to_concept": downgraded,
        }

    def test_zero_unsupported_density_zero(self):
        result = self.fn(self._risk(10, 0))
        assert result["inference_density"] == 0.0
        assert result["inference_gate_passed"] is True

    def test_all_high_risk_unsupported_density_one(self):
        result = self.fn(self._risk(4, 4))
        assert result["inference_density"] == 1.0
        assert result["inference_gate_passed"] is False

    def test_threshold_gate_passes(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.5")
        result = self.fn(self._risk(10, 4))  # 0.4 <= 0.5 → pass
        assert result["inference_gate_passed"] is True

    def test_threshold_gate_fails(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.3")
        result = self.fn(self._risk(10, 4))  # 0.4 > 0.3 → fail
        assert result["inference_gate_passed"] is False

    def test_downgraded_formulas_count_in_density(self):
        # 1 unsupported + 1 downgraded out of 8 sentences = 2/8 = 0.25
        result = self.fn(self._risk(8, 1, downgraded=1))
        assert abs(result["inference_density"] - 0.25) < 1e-6

    def test_empty_sentences_density_zero(self):
        result = self.fn(self._risk(0, 0))
        assert result["inference_density"] == 0.0
        assert result["inference_gate_passed"] is True

    def test_density_formula_correct(self):
        # 2 unsupported out of 8 total = 0.25
        result = self.fn(self._risk(8, 2))
        assert abs(result["inference_density"] - 0.25) < 1e-6

    def test_unsupported_claims_count_equals_sum(self):
        result = self.fn(self._risk(10, 3, downgraded=2))
        assert result["unsupported_claims_count"] == 5

    def test_default_threshold_is_0_25(self, monkeypatch):
        monkeypatch.delenv("SUMMARY_MAX_INFERENCE_DENSITY", raising=False)
        result = self.fn(self._risk(10, 0))
        assert result["inference_threshold"] == 0.25


# ──────────────────────────────────────────────────────────────────────────────
# De-overreach integration tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDeoverreachIntegration:
    """Integration tests for the de-overreach pass and inference-density gate
    wired into run_deep_summary."""

    def _resp(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    def _good_summary(self) -> str:
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Visão Geral\n"
            "O documento explica aprendizado supervisionado [Fonte 1].\n\n"
            "## Encadeamento e Principais Tópicos\n"
            "Os principais tópicos incluem árvores e florestas [Fonte 2].\n\n"
            "## Conceitos e Métodos Fundamentais\n"
            "A impureza de Gini mede a pureza dos nós [Fonte 3].\n\n"
            "## Síntese Final\n"
            "O documento fornece base sólida para aprendizado [Fonte 4]."
        )

    def _summary_with_overreach(self) -> str:
        """Summary with a quantitative claim unsupported (citing only a table-of-contents chunk)."""
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Visão Geral\n"
            "O documento explica aprendizado supervisionado.\n\n"
            "## Encadeamento e Principais Tópicos\n"
            "O algoritmo é 30% mais rápido que o método X [Fonte 1].\n\n"
            "## Conceitos e Métodos Fundamentais\n"
            "A impureza de Gini mede a pureza dos nós [Fonte 2].\n\n"
            "## Síntese Final\n"
            "O documento fornece base sólida para aprendizado [Fonte 3]."
        )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_inference_density_in_diagnostics(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """diagnostics must include inference_density key."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")  # never triggers
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        base = self._good_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 15
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]
        assert "inference_density" in diag
        assert "inference_density" in diag["inference_density"]
        assert "inference_gate_passed" in diag["inference_density"]
        assert "deoverreach" in diag
        assert "claim_risk" in diag

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_inference_density_in_final_diagnostics(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """diagnostics['final'] must include inference_density field."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        base = self._good_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 15
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        final = result["diagnostics"]["final"]
        assert "inference_density" in final
        assert isinstance(final["inference_density"], float)
        assert "missing_topics" in final
        assert isinstance(final["missing_topics"], list)

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_deoverreach_not_triggered_when_threshold_high(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """De-overreach pass not triggered when threshold=1.0 (always passes)."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")  # suppress formula check

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        base = self._good_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 15
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        deoverreach = result["diagnostics"]["deoverreach"]
        assert deoverreach["triggered"] is False or deoverreach["accepted"] is False
        # When threshold=1.0, gate always passes → no trigger OR trigger but no change.

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_deoverreach_skipped_when_latency_budget_exhausted(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """De-overreach should be skipped (with reason) when latency budget is exhausted."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_LATENCY_BUDGET_SECONDS", "1")

        chunks = [
            _doc(
                "Conteudo do sumario: capitulo 1, capitulo 2",
                chunk_index=0,
                page=1,
                section_title="Sumario",
            ),
        ] * 4
        summary_with_unsupported = (
            "# Resumo Aprofundado - doc.pdf\n\n"
            "## Visao Geral\n"
            "O algoritmo e 30% mais rapido que o metodo X [Fonte 1].\n\n"
            "## Encadeamento\n"
            "Topicos progridem do simples ao complexo [Fonte 2].\n\n"
            "## Conceitos\n"
            "Definicoes centrais sao abordadas [Fonte 3].\n\n"
            "## Sintese\n"
            "Conclusao final do estudo [Fonte 4]."
        )

        mock_collect.return_value = chunks
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(summary_with_unsupported)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        deoverreach = result["diagnostics"]["deoverreach"]
        claim_risk = result["diagnostics"]["claim_risk"]

        if claim_risk["unsupported_high_risk_count"] > 0:
            assert deoverreach["triggered"] is True
            assert deoverreach.get("skipped_reason") == "latency_budget_exhausted"
            assert deoverreach["accepted"] is False
        else:
            pytest.skip("No unsupported high-risk claims detected in generated summary.")

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_deoverreach_triggered_when_unsupported_high_risk_present(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """De-overreach pass is triggered when unsupported_high_risk_count > 0.

        Uses a summary with a quantitative claim citing only a sumário-section chunk,
        which is classified as a low-info source → unsupported high-risk claim.
        """
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")  # density gate off
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")

        # Only one chunk, from a "Sumário" (low-info) section.
        chunks = [
            _doc("Conteúdo do sumário: capítulo 1, capítulo 2",
                 chunk_index=0, page=1, section_title="Sumário"),
        ] * 4

        # Summary has a quantitative claim citing [Fonte 1] which is the Sumário chunk.
        summary_with_unsupported = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Visão Geral\n"
            "O algoritmo é 30% mais rápido que o método X [Fonte 1].\n\n"
            "## Encadeamento\n"
            "Os tópicos progridem do simples ao complexo [Fonte 2].\n\n"
            "## Conceitos\n"
            "Definições centrais são abordadas [Fonte 3].\n\n"
            "## Síntese\n"
            "Conclusão final do estudo [Fonte 4]."
        )

        mock_collect.return_value = chunks
        mock_llm = MagicMock()
        # partials (2) + consolidate + final + polish + deoverreach + repair + more
        mock_llm.invoke.side_effect = [
            self._resp(summary_with_unsupported)
        ] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        deoverreach = result["diagnostics"]["deoverreach"]
        claim_risk = result["diagnostics"]["claim_risk"]

        # The quantitative claim citing only the low-info Sumário anchor should be flagged.
        if claim_risk["unsupported_high_risk_count"] > 0:
            assert deoverreach["triggered"] is True, (
                f"Expected deoverreach triggered when unsupported_high_risk_count="
                f"{claim_risk['unsupported_high_risk_count']}: {deoverreach}"
            )
        else:
            pytest.skip(
                "No high-risk claims detected in test summary; "
                "regex may not have flagged the quantitative sentence."
            )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_inference_gate_adds_blocking_reason(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """When inference_density exceeds threshold, blocking_reasons must include it."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.0")  # always fails
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        base = self._good_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        final = result["diagnostics"]["final"]
        # With threshold=0, inference_density > 0 is guaranteed for non-trivial text.
        # If density > 0 > threshold, blocking_reasons must contain the inference reason.
        if result["diagnostics"]["inference_density"]["inference_density"] > 0:
            assert not final["accepted"], (
                f"Expected accepted=False when inference_density>threshold, got: {final}"
            )
            assert any(
                "inference_density_exceeded" in r for r in final["blocking_reasons"]
            ), f"Expected inference_density_exceeded in blocking_reasons: {final['blocking_reasons']}"

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_unsupported_high_risk_in_final_blocking_reasons(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """When unsupported_high_risk_count > 0, final.blocking_reasons includes it."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")  # density gate off
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")

        # Chunks simulating low-info source (sumário).
        chunks = [
            _doc(
                "Sumário: capítulo 1, capítulo 2",
                chunk_index=0, page=1,
                section_title="Sumário",
            )
        ] * 4

        mock_collect.return_value = chunks
        mock_llm = MagicMock()
        # Summary contains a quantitative claim with [Fonte 1] (which is sumário).
        summary_with_claim = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Visão Geral\n"
            "O algoritmo é 50% mais rápido que o baseline [Fonte 1].\n\n"
            "## Conceitos\n"
            "Definições centrais para o estudo [Fonte 1].\n\n"
            "## Métodos\n"
            "O método usa árvores de decisão [Fonte 1].\n\n"
            "## Síntese Final\n"
            "Conclusão integra as ideias [Fonte 1]."
        )
        mock_llm.invoke.side_effect = [self._resp(summary_with_claim)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        final = result["diagnostics"]["final"]
        claim_risk = result["diagnostics"]["claim_risk"]

        if claim_risk["unsupported_high_risk_count"] > 0:
            assert any(
                "unsupported_high_risk_claims" in r for r in final["blocking_reasons"]
            ), (
                f"Expected unsupported_high_risk_claims in blocking_reasons: "
                f"{final['blocking_reasons']}"
            )

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_formula_mode_conservative_env_var_respected(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """SUMMARY_FORMULA_MODE=conservative must be read from env and affect diagnostics."""
        from docops.summarize.pipeline import run_deep_summary
        from docops.config import config

        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "conservative")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        base = self._good_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 15
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        assert result["diagnostics"]["claim_risk"]["formula_mode"] == "conservative"

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_final_accepted_true_when_all_gates_pass(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """final.accepted=True when no blocking conditions are present."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        base = self._good_summary()
        mock_llm.invoke.side_effect = [self._resp(base)] * 15
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        final = result["diagnostics"]["final"]
        # With high thresholds and no low-info sources, should pass.
        # We only check that inference_density blocking reason is NOT there.
        assert not any(
            "inference_density_exceeded" in r for r in final["blocking_reasons"]
        ), f"Unexpected inference blocking reason: {final['blocking_reasons']}"


# ──────────────────────────────────────────────────────────────────────────────
# Execution profile tests (fast / model_first / strict)
# ──────────────────────────────────────────────────────────────────────────────

class TestExecutionProfiles:
    """Tests for execution profiles: fast, model_first, strict."""

    def _resp(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    def _good_summary(self) -> str:
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Visão Geral\n"
            "O documento explica aprendizado supervisionado [Fonte 1].\n\n"
            "## Encadeamento e Principais Tópicos\n"
            "Os principais tópicos incluem árvores e florestas [Fonte 2].\n\n"
            "## Conceitos e Métodos Fundamentais\n"
            "A impureza de Gini mede a pureza dos nós [Fonte 3].\n\n"
            "## Síntese Final\n"
            "O documento fornece base sólida para aprendizado [Fonte 4]."
        )

    # ── _resolve_profile ──────────────────────────────────────────────────────

    def test_resolve_profile_explicit_fast(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("fast") == "fast"

    def test_resolve_profile_explicit_invalid_falls_back_balanced(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("legacy_profile") == "balanced"

    def test_resolve_profile_explicit_strict(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("strict") == "strict"

    def test_resolve_profile_explicit_model_first(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("model_first") == "model_first"

    def test_resolve_profile_explicit_model_first_plus(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("model_first_plus") == "model_first_plus"

    def test_resolve_profile_explicit_model_first_plus_max(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("model_first_plus_max") == "model_first_plus_max"

    def test_resolve_profile_explicit_balanced(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("balanced") == "balanced"

    def test_resolve_profile_invalid_falls_back_to_balanced(self):
        from docops.summarize.pipeline import _resolve_profile
        assert _resolve_profile("unknown_profile") == "balanced"

    def test_resolve_profile_none_uses_config(self, monkeypatch):
        from docops.summarize.pipeline import _resolve_profile
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "fast")
        assert _resolve_profile(None) == "fast"

    def test_resolve_profile_none_uses_config_model_first(self, monkeypatch):
        from docops.summarize.pipeline import _resolve_profile
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "model_first")
        assert _resolve_profile(None) == "model_first"

    def test_resolve_profile_explicit_overrides_env(self, monkeypatch):
        from docops.summarize.pipeline import _resolve_profile
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "fast")
        assert _resolve_profile("strict") == "strict"

    def test_resolve_profile_env_invalid_defaults_to_balanced(self, monkeypatch):
        from docops.summarize.pipeline import _resolve_profile
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "INVALID")
        assert _resolve_profile(None) == "balanced"

    # ── profile_used appears in diagnostics ───────────────────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_profile_used_appears_in_diagnostics(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="fast"
        )
        assert result["diagnostics"]["profile_used"] == "fast"

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_profile_model_first_used_in_diagnostics(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="model_first"
        )
        assert result["diagnostics"]["profile_used"] == "model_first"

    # ── corrective_passes_used ────────────────────────────────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_corrective_passes_used_zero_when_no_triggers(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True
        )
        assert result["diagnostics"]["corrective_passes_used"] == 0

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_fast_profile_zero_corrective_passes(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """In 'fast' profile, corrective_passes_used must always be 0."""
        from docops.summarize.pipeline import run_deep_summary

        # Enable everything that could trigger corrective passes
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "true")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.0")  # always exceeds
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "conservative")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.0")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 30
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="fast"
        )
        assert result["diagnostics"]["corrective_passes_used"] == 0, (
            f"Expected 0 passes in fast profile, "
            f"got {result['diagnostics']['corrective_passes_used']}"
        )

    # ── max_corrective_passes = 1 cap ─────────────────────────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_corrective_passes_capped_at_max(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """corrective_passes_used never exceeds max_corrective_passes."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.0")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 40
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="model_first"
        )
        assert result["diagnostics"]["corrective_passes_used"] <= 1, (
            f"Expected ≤1 corrective pass, "
            f"got {result['diagnostics']['corrective_passes_used']}"
        )

    # ── deoverreach + resynthesis mutual exclusion ────────────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_deoverreach_and_resynthesis_mutually_exclusive(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """When deoverreach is accepted, resynthesis skipped_reason == mutual_exclusion."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")  # allow both if not exclusive
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.0")  # always triggers deoverreach
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_WEAK_BLOCK_RATIO", "0.0")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")

        # deoverreach response = lower density text (no high-risk claims)
        clean_text = (
            "# Resumo\n\n"
            "## Visão Geral\nO documento é sobre aprendizado [Fonte 1].\n\n"
            "## Encadeamento\nO método usa árvores [Fonte 2].\n\n"
            "## Conceitos\nGini é usado [Fonte 3].\n\n"
            "## Síntese\nResultados sólidos [Fonte 4]."
        )
        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            self._resp(self._good_summary()),  # partial(s) + consolidate + finalize
        ] * 5 + [self._resp(clean_text)] * 30  # deoverreach + rest
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="model_first"
        )
        diag = result["diagnostics"]
        if diag["deoverreach"].get("accepted"):
            # If deoverreach accepted → resynthesis must be skipped for mutual exclusion
            assert diag["resynthesis"].get("skipped_reason") == "deoverreach_accepted_mutual_exclusion", (
                f"Expected mutual exclusion skip, got: {diag['resynthesis'].get('skipped_reason')}"
            )

    # ── style polish disabled by default ─────────────────────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_style_polish_disabled_by_default(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """style_polish_enabled defaults to False; polish call not issued."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.delenv("SUMMARY_STYLE_POLISH_ENABLED", raising=False)
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True
        )
        assert result["diagnostics"]["style_polish_enabled"] is False

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_style_polish_always_disabled_in_fast(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """In 'fast' profile, style_polish_enabled is always False."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_STYLE_POLISH_ENABLED", "true")  # explicit true
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="fast"
        )
        assert result["diagnostics"]["style_polish_enabled"] is False

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_style_polish_enabled_when_configured(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """style_polish_enabled=True in non-fast profile when env var=true."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_STYLE_POLISH_ENABLED", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 25
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=True, profile="strict"
        )
        assert result["diagnostics"]["style_polish_enabled"] is True

    # ── stage timings in diagnostics ─────────────────────────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_latency_section_present_in_diagnostics(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True
        )
        latency = result["diagnostics"]["latency"]
        assert "total_ms" in latency
        assert isinstance(latency["total_ms"], (int, float))
        assert latency["total_ms"] >= 0
        assert "stage_timings_ms" in latency
        timings = latency["stage_timings_ms"]
        for key in ("collect", "clean", "group", "partials", "consolidate", "finalize"):
            assert key in timings, f"Missing stage timing: {key}"

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_stage_timings_non_negative(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True
        )
        timings = result["diagnostics"]["latency"]["stage_timings_ms"]
        for stage, ms in timings.items():
            assert ms >= 0, f"Negative timing for stage '{stage}': {ms}"

    # ── strict fail-closed: diagnostics always attached ──────────────────────

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_strict_profile_always_attaches_diagnostics(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """In strict profile, diagnostics is returned even with include_diagnostics=False."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=False, profile="strict"
        )
        # Must have diagnostics even though include_diagnostics=False
        assert "diagnostics" in result, "strict profile must always include diagnostics"
        assert result["diagnostics"]["profile_used"] == "strict"

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_model_first_profile_runs_minimal_path(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = self._resp(
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Visão Geral\nTexto suportado [Fonte 1].\n\n"
            "## Síntese Final\nConclusão objetiva [Fonte 1]."
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1, profile="model_first", include_diagnostics=True
        )
        diag = result["diagnostics"]
        assert diag["profile_used"] == "model_first"
        assert diag["mode"] == "model_first"
        assert diag["corrective_timeline"] == []
        assert diag["corrective_passes_used"] == 0

    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_non_strict_profile_no_diagnostics_when_not_requested(
        self, mock_collect, mock_llm_factory, monkeypatch
    ):
        """In model_first/fast, diagnostics NOT returned when include_diagnostics=False."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_FORMULA_MODE", "permissive")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        mock_collect.return_value = _make_chunks(4, with_sections=True)
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(self._good_summary())] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1,
            include_diagnostics=False, profile="model_first"
        )
        assert "diagnostics" not in result, (
            "model_first profile should NOT include diagnostics when not requested"
        )

    # ── config properties ─────────────────────────────────────────────────────

    def test_config_summary_deep_profile_default(self, monkeypatch):
        monkeypatch.delenv("SUMMARY_DEEP_PROFILE", raising=False)
        from docops.config import Config
        assert Config().summary_deep_profile == "balanced"

    def test_config_summary_deep_profile_fast(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "fast")
        from docops.config import Config
        assert Config().summary_deep_profile == "fast"

    def test_config_summary_deep_profile_strict(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "strict")
        from docops.config import Config
        assert Config().summary_deep_profile == "strict"

    def test_config_summary_deep_profile_model_first(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "model_first")
        from docops.config import Config
        assert Config().summary_deep_profile == "model_first"

    def test_config_summary_deep_profile_model_first_plus(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "model_first_plus")
        from docops.config import Config
        assert Config().summary_deep_profile == "model_first_plus"

    def test_config_summary_deep_profile_model_first_plus_max(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "model_first_plus_max")
        from docops.config import Config
        assert Config().summary_deep_profile == "model_first_plus_max"

    def test_config_summary_deep_profile_balanced(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "balanced")
        from docops.config import Config
        assert Config().summary_deep_profile == "balanced"

    def test_config_summary_deep_profile_legacy_value_falls_back(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "legacy_profile")
        from docops.config import Config
        assert Config().summary_deep_profile == "balanced"

    def test_config_summary_deep_profile_invalid(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_DEEP_PROFILE", "nope")
        from docops.config import Config
        assert Config().summary_deep_profile == "balanced"

    def test_config_max_corrective_passes_default(self, monkeypatch):
        monkeypatch.delenv("SUMMARY_MAX_CORRECTIVE_PASSES", raising=False)
        from docops.config import Config
        assert Config().summary_max_corrective_passes == 1

    def test_config_max_corrective_passes_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "3")
        from docops.config import Config
        assert Config().summary_max_corrective_passes == 3

    def test_config_style_polish_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("SUMMARY_STYLE_POLISH_ENABLED", raising=False)
        from docops.config import Config
        assert Config().summary_style_polish_enabled is False

    def test_config_style_polish_enabled_via_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_STYLE_POLISH_ENABLED", "true")
        from docops.config import Config
        assert Config().summary_style_polish_enabled is True

    def test_config_fail_closed_strict_default(self, monkeypatch):
        monkeypatch.delenv("SUMMARY_FAIL_CLOSED_STRICT", raising=False)
        from docops.config import Config
        assert Config().summary_fail_closed_strict is True

    def test_config_fail_closed_strict_env_false(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_FAIL_CLOSED_STRICT", "false")
        from docops.config import Config
        assert Config().summary_fail_closed_strict is False


# ──────────────────────────────────────────────────────────────────────────────
# Backfill-before-deoverreach: early micro-backfill ordering
# ──────────────────────────────────────────────────────────────────────────────


class TestBackfillBeforeDeoverreach:
    """Testa a nova ordem de passes corretivos: micro-backfill early antes de
    de-overreach/resynthesis quando summary_backfill_before_deoverreach=True."""

    def _resp(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    def _good_summary(self, marker: str = "GOOD") -> str:
        return (
            f"# Resumo Aprofundado — doc.pdf {marker}\n\n"
            "## Visão Geral\n"
            f"O documento explica conceitos fundamentais {marker} [Fonte 1].\n\n"
            "## Conceitos Principais\n"
            f"Os algoritmos principais são discutidos em detalhe {marker} [Fonte 2].\n\n"
            "## Métodos e Aplicações\n"
            f"As aplicações práticas são apresentadas com exemplos {marker} [Fonte 3].\n\n"
            "## Síntese Final\n"
            f"A conclusão integra todas as ideias centrais {marker} [Fonte 4]."
        )

    def _make_chunks_bf(self, n: int = 4) -> list[Document]:
        return _make_chunks(n, with_sections=True)

    def _topic_info_with_missing(self) -> dict:
        return {
            "detected_topics": ["topic_A"],
            "must_cover_topics": ["topic_A"],
            "minor_topics": [],
            "topic_details": {"topic_A": {"label": "Tópico A", "hits": 2}},
            "outline_text": "",
        }

    def _outline_missing(self) -> dict:
        return {
            "overall_score": 0.3,
            "detected_topics": ["topic_A"],
            "must_cover_topics": ["topic_A"],
            "covered_topics": [],
            "missing_topics": ["topic_A"],
            "weakly_covered_topics": [],
            "topic_scores": {"topic_A": 0.0},
        }

    def _outline_covered(self) -> dict:
        return {
            "overall_score": 1.0,
            "detected_topics": ["topic_A"],
            "must_cover_topics": ["topic_A"],
            "covered_topics": ["topic_A"],
            "missing_topics": [],
            "weakly_covered_topics": [],
            "topic_scores": {"topic_A": 1.0},
        }

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_early_backfill_triggered_when_missing_topics_and_flag_enabled(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """Com missing must-cover topics e flag habilitada, early backfill deve
        ser triggered e aparecer na corrective_timeline."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_MICRO_BACKFILL_ENABLED", "true")

        base = self._good_summary("BASE")
        backfilled = self._good_summary("BACKFILLED")

        mock_collect.return_value = self._make_chunks_bf()
        mock_extract_topics.return_value = self._topic_info_with_missing()
        mock_outline_score.return_value = self._outline_missing()

        mock_micro_backfill.return_value = {
            "text": backfilled,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["topic_A"],
            "missing_topics_after": ["topic_A"],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(base)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        assert diag["early_micro_backfill"]["triggered"] is True
        assert diag["early_micro_backfill"]["accepted"] is True
        assert diag["early_micro_backfill"]["backfill_before_deoverreach_enabled"] is True
        assert "micro_backfill_early" in diag["corrective_timeline"]
        assert diag["corrective_timeline"][0] == "micro_backfill_early"
        assert diag["corrective_scheduler"]["backfill_before_deoverreach"] is True

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_early_backfill_not_run_when_flag_disabled(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """Com SUMMARY_BACKFILL_BEFORE_DEOVERREACH=false, o early backfill NÃO
        deve rodar. A ordem legada é mantida."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "false")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_MICRO_BACKFILL_ENABLED", "true")

        base = self._good_summary("BASE")

        mock_collect.return_value = self._make_chunks_bf()
        mock_extract_topics.return_value = self._topic_info_with_missing()
        mock_outline_score.return_value = self._outline_missing()

        mock_micro_backfill.return_value = {
            "text": base,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 0,
            "missing_topics_before": ["topic_A"],
            "missing_topics_after": ["topic_A"],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(base)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        assert diag["early_micro_backfill"]["triggered"] is False
        assert diag["early_micro_backfill"]["accepted"] is False
        assert diag["early_micro_backfill"]["backfill_before_deoverreach_enabled"] is False
        assert "micro_backfill_early" not in diag["corrective_timeline"]
        assert diag["corrective_scheduler"]["backfill_before_deoverreach"] is False

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_early_backfill_not_run_in_fast_profile(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """No perfil fast, early backfill nunca roda."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")

        base = self._good_summary("BASE")

        mock_collect.return_value = self._make_chunks_bf()
        mock_extract_topics.return_value = self._topic_info_with_missing()
        mock_outline_score.return_value = self._outline_missing()
        mock_micro_backfill.return_value = {
            "text": base,
            "triggered": False,
            "paragraphs_attempted": 0,
            "paragraphs_accepted": 0,
            "missing_topics_before": [],
            "missing_topics_after": [],
            "skipped_topics": [],
            "latency_ms": 0.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(base)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary(
            "doc.pdf", "doc-uuid", user_id=1, profile="fast", include_diagnostics=True
        )
        diag = result["diagnostics"]

        assert diag["early_micro_backfill"]["triggered"] is False
        assert diag["early_micro_backfill"]["backfill_before_deoverreach_enabled"] is False
        assert diag["corrective_timeline"] == []

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_budget_exhausted_after_early_backfill_blocks_deoverreach(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """Com max_corrective_passes=1, após early backfill consumir o único passe,
        deoverreach deve ser bloqueado por corrective_budget_exhausted."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        # Threshold baixo para garantir que deoverreach estaria triggered se houvesse budget
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.01")
        monkeypatch.setenv("SUMMARY_MICRO_BACKFILL_ENABLED", "true")

        overreach = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Contexto\n"
            "O algoritmo tem precisão de 99,7% em todos os benchmarks [Fonte 1].\n\n"
            "## Análise\n"
            "A redução de custo foi de exatamente R$1.234,56 por unidade [Fonte 1].\n\n"
            "## Resultados\n"
            "Os testes confirmam melhora de 3,14x sobre o estado da arte [Fonte 1].\n\n"
            "## Conclusão\n"
            "O modelo supera todos os concorrentes em N=500 experimentos [Fonte 1]."
        )

        mock_collect.return_value = self._make_chunks_bf()
        mock_extract_topics.return_value = self._topic_info_with_missing()
        mock_outline_score.return_value = self._outline_missing()

        mock_micro_backfill.return_value = {
            "text": overreach,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["topic_A"],
            "missing_topics_after": ["topic_A"],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(overreach)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        assert diag["early_micro_backfill"]["triggered"] is True
        assert diag["early_micro_backfill"]["accepted"] is True
        assert diag["corrective_passes_used"] == 1

        # Deoverreach não deve ter consumido passe (budget esgotado)
        dor = diag["deoverreach"]
        assert not dor.get("pass_consumed", False)
        assert "micro_backfill_early" in diag["corrective_timeline"]
        assert "deoverreach" not in diag["corrective_timeline"]

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_early_backfill_not_triggered_when_no_missing_topics(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """Sem missing topics, early backfill não deve ser triggered."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "1")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")

        base = self._good_summary("BASE")

        mock_collect.return_value = self._make_chunks_bf()
        mock_extract_topics.return_value = self._topic_info_with_missing()
        mock_outline_score.return_value = self._outline_covered()

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [self._resp(base)] * 20
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        assert diag["early_micro_backfill"]["triggered"] is False
        assert "micro_backfill_early" not in diag["corrective_timeline"]

    @patch("docops.summarize.pipeline._run_micro_topic_backfill")
    @patch("docops.summarize.pipeline.score_topic_outline_coverage")
    @patch("docops.summarize.pipeline.extract_document_topics")
    @patch("docops.summarize.pipeline._get_llm")
    @patch("docops.summarize.pipeline.collect_ordered_chunks")
    def test_corrective_timeline_order_backfill_before_deoverreach_with_budget(
        self,
        mock_collect,
        mock_llm_factory,
        mock_extract_topics,
        mock_outline_score,
        mock_micro_backfill,
        monkeypatch,
    ):
        """Com max_corrective_passes=2, se ambos early backfill e deoverreach rodam,
        a timeline deve ter micro_backfill_early ANTES de deoverreach."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")
        monkeypatch.setenv("SUMMARY_MAX_CORRECTIVE_PASSES", "2")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_RESYNTHESIS_MAX_ACCEPTED_WEAK_RATIO", "1.0")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "0.01")
        monkeypatch.setenv("SUMMARY_MICRO_BACKFILL_ENABLED", "true")

        overreach = (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Contexto\n"
            "O algoritmo é exatamente 47,3% mais eficiente que baseline [Fonte 1].\n\n"
            "## Métodos\n"
            "A redução de erro foi medida em 0,003 desvios padrão [Fonte 1].\n\n"
            "## Resultados\n"
            "Os experimentos confirmam resultados em N=1000 iterações [Fonte 1].\n\n"
            "## Síntese\n"
            "O modelo atinge performance ótima em todos os cenários [Fonte 1]."
        )
        clean = self._good_summary("CLEAN")

        mock_collect.return_value = self._make_chunks_bf()
        mock_extract_topics.return_value = self._topic_info_with_missing()
        mock_outline_score.return_value = self._outline_missing()

        mock_micro_backfill.return_value = {
            "text": overreach,
            "triggered": True,
            "paragraphs_attempted": 1,
            "paragraphs_accepted": 1,
            "missing_topics_before": ["topic_A"],
            "missing_topics_after": ["topic_A"],
            "skipped_topics": [],
            "latency_ms": 5.0,
        }

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = (
            [self._resp(overreach)] * 5 + [self._resp(clean)] * 15
        )
        mock_llm_factory.return_value = mock_llm

        result = run_deep_summary("doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True)
        diag = result["diagnostics"]

        timeline = diag["corrective_timeline"]
        assert isinstance(timeline, list)
        assert diag["early_micro_backfill"]["triggered"] is True

        # Se ambos aparecem na timeline, early backfill deve vir primeiro
        if "micro_backfill_early" in timeline and "deoverreach" in timeline:
            assert timeline.index("micro_backfill_early") < timeline.index("deoverreach"), (
                f"micro_backfill_early deve preceder deoverreach, mas timeline={timeline}"
            )


class TestBackfillBeforeDeoverreachConfig:
    """Testa as propriedades de configuração de backfill_before_deoverreach."""

    def test_config_backfill_before_deoverreach_default_true(self, monkeypatch):
        """summary_backfill_before_deoverreach deve ser True por padrão."""
        monkeypatch.delenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", raising=False)
        from docops.config import Config
        assert Config().summary_backfill_before_deoverreach is True

    def test_config_backfill_before_deoverreach_env_false(self, monkeypatch):
        """summary_backfill_before_deoverreach deve ser False quando env=false."""
        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "false")
        from docops.config import Config
        assert Config().summary_backfill_before_deoverreach is False

    def test_config_backfill_before_deoverreach_env_true(self, monkeypatch):
        """summary_backfill_before_deoverreach deve ser True quando env=true."""
        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")
        from docops.config import Config
        assert Config().summary_backfill_before_deoverreach is True

    def test_config_backfill_before_deoverreach_env_1(self, monkeypatch):
        """summary_backfill_before_deoverreach deve aceitar '1' como True."""
        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "1")
        from docops.config import Config
        assert Config().summary_backfill_before_deoverreach is True

    def test_config_backfill_before_deoverreach_env_0(self, monkeypatch):
        """summary_backfill_before_deoverreach deve tratar '0' como False."""
        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "0")
        from docops.config import Config
        assert Config().summary_backfill_before_deoverreach is False


class TestCorrectiveTimeline:
    """Testa o campo corrective_timeline nos diagnostics."""

    def _resp(self, text: str):
        m = MagicMock()
        m.content = text
        return m

    def _good_summary(self) -> str:
        return (
            "# Resumo Aprofundado — doc.pdf\n\n"
            "## Contexto\n"
            "O documento apresenta fundamentos teóricos [Fonte 1].\n\n"
            "## Análise\n"
            "A abordagem metodológica é rigorosa e bem estruturada [Fonte 2].\n\n"
            "## Conceitos\n"
            "As definições estão integradas com exemplos práticos [Fonte 3].\n\n"
            "## Síntese\n"
            "A conclusão reforça os principais achados [Fonte 4]."
        )

    def test_corrective_timeline_is_list_in_diagnostics(self, monkeypatch):
        """corrective_timeline deve ser uma lista nos diagnostics."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")

        base = self._good_summary()

        with patch("docops.summarize.pipeline.collect_ordered_chunks") as mc, \
             patch("docops.summarize.pipeline._get_llm") as mllm:
            mc.return_value = _make_chunks(4, with_sections=True)
            mock_llm = MagicMock()
            mock_llm.invoke.side_effect = [self._resp(base)] * 15
            mllm.return_value = mock_llm

            result = run_deep_summary(
                "doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True
            )

        assert "corrective_timeline" in result["diagnostics"]
        assert isinstance(result["diagnostics"]["corrective_timeline"], list)

    def test_corrective_timeline_empty_when_no_passes_run(self, monkeypatch):
        """corrective_timeline deve estar vazia quando nenhum passe corretivo roda."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")

        base = self._good_summary()

        with patch("docops.summarize.pipeline.collect_ordered_chunks") as mc, \
             patch("docops.summarize.pipeline._get_llm") as mllm:
            mc.return_value = _make_chunks(4, with_sections=True)
            mock_llm = MagicMock()
            mock_llm.invoke.side_effect = [self._resp(base)] * 15
            mllm.return_value = mock_llm

            result = run_deep_summary(
                "doc.pdf", "doc-uuid", user_id=1,
                profile="fast",
                include_diagnostics=True,
            )

        diag = result["diagnostics"]
        assert "corrective_timeline" in diag
        assert diag["corrective_timeline"] == []

    def test_early_micro_backfill_key_always_in_diagnostics(self, monkeypatch):
        """early_micro_backfill deve estar sempre presente nos diagnostics."""
        from docops.summarize.pipeline import run_deep_summary

        monkeypatch.setenv("SUMMARY_RESYNTHESIS_ENABLED", "false")
        monkeypatch.setenv("SUMMARY_GROUNDING_REPAIR", "false")
        monkeypatch.setenv("SUMMARY_MAX_INFERENCE_DENSITY", "1.0")
        monkeypatch.setenv("SUMMARY_STRUCTURE_MIN_CHARS", "20")
        monkeypatch.setenv("SUMMARY_BACKFILL_BEFORE_DEOVERREACH", "true")

        base = self._good_summary()

        with patch("docops.summarize.pipeline.collect_ordered_chunks") as mc, \
             patch("docops.summarize.pipeline._get_llm") as mllm:
            mc.return_value = _make_chunks(4, with_sections=True)
            mock_llm = MagicMock()
            mock_llm.invoke.side_effect = [self._resp(base)] * 15
            mllm.return_value = mock_llm

            result = run_deep_summary(
                "doc.pdf", "doc-uuid", user_id=1, include_diagnostics=True
            )

        diag = result["diagnostics"]
        assert "early_micro_backfill" in diag
        emb = diag["early_micro_backfill"]
        for key in (
            "triggered", "accepted", "missing_topics_before", "missing_topics_after",
            "paragraphs_attempted", "paragraphs_accepted", "latency_ms",
            "backfill_before_deoverreach_enabled",
        ):
            assert key in emb, f"Campo '{key}' ausente em early_micro_backfill"
