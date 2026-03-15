"""Tests for improved coverage detection and false-positive prevention.

These tests verify that:
1. The improved formula signal detection catches ASCII math and Greek names.
2. The improved concept detection works for slides/PDFs.
3. The topic-aware anchor selection covers late-document sections.
4. A summary cannot pass quality gates while missing major topics.
"""

import pytest
from langchain_core.documents import Document

from docops.summarize.pipeline import (
    detect_coverage_signals,
    score_coverage,
    _select_citation_anchors,
    compute_summary_rubric,
    _COVERAGE_FORMULA_SIGNAL_RE,
    _COVERAGE_CONCEPT_SIGNAL_RE,
    _COVERAGE_FORMULA_SUMMARY_RE,
    _COVERAGE_CONCEPT_SUMMARY_RE,
)
from docops.summarize.outline import (
    extract_document_topics,
    score_topic_outline_coverage,
)


def _make_chunk(text: str, idx: int = 0) -> Document:
    return Document(
        page_content=text,
        metadata={"chunk_index": idx, "file_type": "pdf", "page": idx + 1,
                   "page_start": idx + 1, "page_end": idx + 1},
    )


# ── Formula signal detection (improved) ──────────────────────────────────────

class TestFormulaSignalDetection:
    def test_ascii_argmin(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("argmin(f(x))")

    def test_ascii_log2(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("H(S) = -sum p_i * log2(p_i)")

    def test_subscript_notation(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("p_i denotes the probability of class i")

    def test_cardinality_notation(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("where |T| is the number of leaf nodes")

    def test_greek_name_alpha(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("the alpha parameter controls complexity")

    def test_greek_name_sigma(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("sigma represents the standard deviation")

    def test_fraction_pattern(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("the ratio a/b determines the split")

    def test_latex_macro(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("\\frac{a}{b}")

    def test_sum_notation(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("sum(i=1 to n)")

    def test_o_notation(self):
        assert _COVERAGE_FORMULA_SIGNAL_RE.search("O(n log n)")


class TestFormulaSummaryDetection:
    def test_ascii_argmin_in_summary(self):
        assert _COVERAGE_FORMULA_SUMMARY_RE.search("argmin over all attributes")

    def test_cardinality_in_summary(self):
        assert _COVERAGE_FORMULA_SUMMARY_RE.search("|T| represents the number of leaves")

    def test_greek_name_in_summary(self):
        assert _COVERAGE_FORMULA_SUMMARY_RE.search("the alpha parameter for pruning")


# ── Concept signal detection (improved for PDFs/slides) ───────────────────────

class TestConceptSignalDetection:
    def test_colon_definition(self):
        assert _COVERAGE_CONCEPT_SIGNAL_RE.search("Entropia: medida de incerteza em um conjunto")

    def test_english_definition(self):
        assert _COVERAGE_CONCEPT_SIGNAL_RE.search("Information gain is defined as the reduction in entropy")

    def test_pt_definition(self):
        assert _COVERAGE_CONCEPT_SIGNAL_RE.search("Índice de Gini consiste em uma métrica de impureza")

    def test_caps_concept_in_slides(self):
        assert _COVERAGE_CONCEPT_SIGNAL_RE.search("OVERFITTING ocorre quando o modelo memoriza o ruído")

    def test_bold_markdown_term(self):
        assert _COVERAGE_CONCEPT_SIGNAL_RE.search("**Árvore de Decisão** é um modelo de classificação")

    def test_bullet_concept(self):
        text = "- Entropia: medida de desordem no sistema"
        assert _COVERAGE_CONCEPT_SIGNAL_RE.search(text)


class TestConceptSummaryDetection:
    def test_concept_keyword(self):
        assert _COVERAGE_CONCEPT_SUMMARY_RE.search("o conceito de entropia")

    def test_fundamental_keyword(self):
        assert _COVERAGE_CONCEPT_SUMMARY_RE.search("os fundamentos teóricos")

    def test_approach_keyword(self):
        assert _COVERAGE_CONCEPT_SUMMARY_RE.search("the approach uses greedy heuristics")

    def test_framework_keyword(self):
        assert _COVERAGE_CONCEPT_SUMMARY_RE.search("this framework combines multiple models")


# ── Improved anchor selection ─────────────────────────────────────────────────

class TestImprovedAnchorSelection:
    def test_topic_aware_anchors(self):
        """Anchors should cover topics, not just first chunk per group."""
        chunks = [
            _make_chunk("Introduction to machine learning and algorithms.", 0),
            _make_chunk("Classification models predict discrete labels.", 1),
            _make_chunk("The algorithm uses entropy as split criterion.", 2),
            _make_chunk("Random forest combines multiple decision trees as an ensemble variant.", 3),
            _make_chunk("Cross-validation evaluates generalization performance.", 4),
            _make_chunk("Pruning regularization controls overfitting.", 5),
            _make_chunk("Regression trees predict continuous values using variance reduction.", 6),
            _make_chunk("The VC dimension bounds the generalization error.", 7),
        ]
        groups = [chunks[:2], chunks[2:4], chunks[4:6], chunks[6:]]
        topic_info = extract_document_topics(chunks)

        anchors = _select_citation_anchors(
            chunks, groups, max_anchors=8, topic_info=topic_info
        )

        # Should have anchors from different parts of the document.
        anchor_indices = set()
        for a in anchors:
            for i, c in enumerate(chunks):
                if id(a) == id(c):
                    anchor_indices.add(i)
        # Late-document chunks (indices 6, 7) should be represented.
        assert any(i >= 6 for i in anchor_indices), (
            f"No late-document anchors selected. Indices: {anchor_indices}"
        )

    def test_picks_richest_chunk_per_group(self):
        """Anchor selection should prefer content-rich chunks over first-in-group."""
        short = _make_chunk("Short.", 0)
        long = _make_chunk("This is a much longer chunk with substantial content about machine learning.", 1)
        groups = [[short, long]]
        anchors = _select_citation_anchors([short, long], groups, max_anchors=1)
        assert anchors[0] is long

    def test_without_topic_info(self):
        """Should still work when topic_info is None (backward compatible)."""
        chunks = [_make_chunk(f"Chunk {i} content.", i) for i in range(6)]
        groups = [chunks[:3], chunks[3:]]
        anchors = _select_citation_anchors(chunks, groups, max_anchors=4)
        assert len(anchors) <= 4


# ── Rubric with outline score ─────────────────────────────────────────────────

class TestRubricWithOutlineScore:
    def test_low_outline_score_lowers_rubric(self):
        """When major topics are missing, rubric should reflect this."""
        rubric_good = compute_summary_rubric(
            structure_valid=True, weak_ratio=0.0,
            unique_sources=5, min_unique_sources=5,
            coverage_score=1.0, facet_score=1.0,
            claims_score=1.0, notation_score=1.0,
            outline_score=1.0,
        )
        rubric_bad = compute_summary_rubric(
            structure_valid=True, weak_ratio=0.0,
            unique_sources=5, min_unique_sources=5,
            coverage_score=1.0, facet_score=1.0,
            claims_score=1.0, notation_score=1.0,
            outline_score=0.3,  # 3 of 10 topics covered.
        )
        assert rubric_bad["overall_score"] < rubric_good["overall_score"]
        assert rubric_bad["outline_score"] == 0.3

    def test_perfect_rubric_requires_good_outline(self):
        """Cannot achieve near-perfect rubric with low outline score."""
        rubric = compute_summary_rubric(
            structure_valid=True, weak_ratio=0.0,
            unique_sources=5, min_unique_sources=5,
            coverage_score=1.0, facet_score=1.0,
            claims_score=1.0, notation_score=1.0,
            outline_score=0.4,
        )
        # With outline weight 0.20, a score of 0.4 should drag overall below 0.90.
        assert rubric["overall_score"] < 0.90


# ── False-positive prevention integration test ───────────────────────────────

class TestFalsePositivePrevention:
    """Critical regression tests: ensure the system can no longer claim perfect
    coverage while missing major document topics."""

    def _simulate_document(self) -> tuple[list[Document], dict]:
        """Simulate a document with many distinct major topics."""
        chunks = [
            _make_chunk("Introduction: supervised learning and classification taxonomy. "
                        "Machine learning algorithms are classified into supervised and unsupervised families.", 0),
            _make_chunk("The classification algorithm constructs a decision tree by recursively partitioning "
                        "the training data. Each split uses a greedy heuristic procedure.", 1),
            _make_chunk("The split criterion selects the attribute that maximizes information gain, "
                        "computed as the entropy reduction: H(S) = -sum p_i log2(p_i).", 2),
            _make_chunk("Pruning regularization controls overfitting by removing branches. "
                        "Cost-complexity pruning uses alpha_eff parameter to balance tree size.", 3),
            _make_chunk("The VC dimension bounds generalization error. Vapnik-Chervonenkis theory "
                        "provides the theoretical foundation for model complexity control.", 4),
            _make_chunk("Random forest is an ensemble variant that combines multiple trees via bagging. "
                        "Boosting uses sequential weak learners for improved accuracy.", 5),
            _make_chunk("Regression trees predict continuous values by minimizing variance reduction "
                        "at each split. Mean squared error is the loss function.", 6),
            _make_chunk("Cross-validation evaluates model performance. K-fold validation splits data "
                        "into k partitions and averages the test accuracy.", 7),
            _make_chunk("For example, consider a dataset of customer purchase patterns. "
                        "This benchmark demonstrates the application on a real-world problem.", 8),
        ]
        topic_info = extract_document_topics(chunks)
        return chunks, topic_info

    def test_fluent_but_incomplete_summary_scores_low(self):
        """A summary that sounds good but only covers 2 of 7+ topics should fail."""
        _chunks, topic_info = self._simulate_document()

        incomplete_summary = (
            "## Visão Geral\n"
            "Este documento apresenta uma visão abrangente sobre árvores de decisão.\n\n"
            "## Encadeamento e Principais Tópicos\n"
            "O documento cobre diversos aspectos do modelo.\n\n"
            "## Conceitos Fundamentais\n"
            "A construção da árvore utiliza um algoritmo recursivo que particiona os dados "
            "selecionando o melhor atributo a cada nó. O procedimento greedy avalia todos "
            "os possíveis splits.\n\n"
            "## Aplicações e Variações\n"
            "O modelo é versátil e amplamente utilizado.\n\n"
            "## Síntese Final\n"
            "Em resumo, árvores de decisão são modelos interpretáveis e eficientes."
        )

        result = score_topic_outline_coverage(incomplete_summary, topic_info)
        # Must detect missing topics.
        assert len(result["missing_topics"]) >= 3, (
            f"Expected >=3 missing topics, got {len(result['missing_topics'])}: {result['missing_topics']}"
        )
        # Overall score should be well below 1.0.
        assert result["overall_score"] < 0.6, (
            f"Expected score < 0.6, got {result['overall_score']:.2f}"
        )

    def test_complete_summary_scores_high(self):
        """A summary that explains all topics should score well."""
        _chunks, topic_info = self._simulate_document()

        complete_summary = (
            "## Visão Geral\n"
            "Este documento apresenta uma introdução a árvores de decisão no contexto "
            "de aprendizado supervisionado. A taxonomia de classificação distingue entre "
            "métodos supervisionados e não supervisionados.\n\n"
            "## Construção do Modelo\n"
            "O algoritmo constrói a árvore recursivamente usando uma heurística gulosa que "
            "particiona os dados em cada nó. O critério de seleção avalia todos os atributos "
            "e escolhe aquele que maximiza o ganho de informação, calculado como a redução "
            "de entropia: H(S) = -sum p_i * log2(p_i). O índice de Gini é uma alternativa.\n\n"
            "## Regularização e Generalização\n"
            "Para controlar overfitting, técnicas de poda são aplicadas. Cost-complexity pruning "
            "usa o parâmetro alpha_eff para balancear tamanho da árvore e acurácia. A teoria VC "
            "de Vapnik-Chervonenkis fundamenta o controle de complexidade e fornece limites para "
            "o erro de generalização.\n\n"
            "## Variantes e Extensões\n"
            "Random forest é uma variante ensemble que combina múltiplas árvores via bagging. "
            "Boosting usa aprendizes fracos sequenciais. Árvores de regressão predizem valores "
            "contínuos minimizando a redução de variância. O MSE é a função de perda padrão.\n\n"
            "## Avaliação e Aplicações\n"
            "Cross-validation com k-fold avalia a performance do modelo dividindo os dados em "
            "k partições. O hiperparâmetro de poda é selecionado via validação cruzada. "
            "Por exemplo, um dataset de padrões de compra demonstra a aplicação prática."
        )

        result = score_topic_outline_coverage(complete_summary, topic_info)
        assert result["overall_score"] >= 0.7, (
            f"Expected score >= 0.7, got {result['overall_score']:.2f}. "
            f"Missing: {result['missing_topics']}"
        )

    def test_rubric_reflects_missing_topics(self):
        """The rubric should produce a lower overall score when topics are missing."""
        _chunks, topic_info = self._simulate_document()

        incomplete_summary = "## Overview\nA brief summary about classification."
        complete_summary = (
            "This algorithm constructs a decision tree using entropy as the split criterion. "
            "Pruning regularization controls overfitting. The VC dimension bounds generalization. "
            "Random forest is an ensemble variant. Regression trees minimize variance. "
            "Cross-validation evaluates the model. Introduction covers the classification taxonomy."
        )

        incomplete_score = score_topic_outline_coverage(incomplete_summary, topic_info)
        complete_score = score_topic_outline_coverage(complete_summary, topic_info)

        rubric_incomplete = compute_summary_rubric(
            structure_valid=True, weak_ratio=0.0,
            unique_sources=5, min_unique_sources=5,
            coverage_score=1.0, facet_score=1.0,
            claims_score=1.0, notation_score=1.0,
            outline_score=incomplete_score["overall_score"],
        )
        rubric_complete = compute_summary_rubric(
            structure_valid=True, weak_ratio=0.0,
            unique_sources=5, min_unique_sources=5,
            coverage_score=1.0, facet_score=1.0,
            claims_score=1.0, notation_score=1.0,
            outline_score=complete_score["overall_score"],
        )
        assert rubric_incomplete["overall_score"] < rubric_complete["overall_score"]
