"""Tests for document outline / topic extraction (docops.summarize.outline)."""

import pytest
from langchain_core.documents import Document

from docops.summarize.outline import (
    extract_document_topics,
    score_topic_outline_coverage,
    get_topic_anchors,
)


def _make_chunk(text: str, idx: int = 0) -> Document:
    return Document(
        page_content=text,
        metadata={"chunk_index": idx, "file_type": "pdf", "page": idx + 1},
    )


# ── Topic extraction tests ────────────────────────────────────────────────────

class TestExtractDocumentTopics:
    def test_detects_core_method_topic(self):
        chunks = [
            _make_chunk("The algorithm constructs a decision tree top-down using a greedy heuristic.", 0),
            _make_chunk("The construction procedure partitions the data at each node.", 1),
            _make_chunk("The recursive procedure splits on the best attribute.", 2),
        ]
        info = extract_document_topics(chunks)
        assert "core_method" in info["detected_topics"]
        assert "core_method" in info["must_cover_topics"]

    def test_detects_regularization_topic(self):
        chunks = [
            _make_chunk("Pruning reduces overfitting by removing branches that add little predictive power.", 0),
            _make_chunk("Cost-complexity pruning uses alpha_eff parameter to control tree size.", 1),
            _make_chunk("Regularization via early stopping prevents the model from memorizing noise.", 2),
        ]
        info = extract_document_topics(chunks)
        assert "regularization" in info["detected_topics"]

    def test_detects_multiple_topics(self):
        chunks = [
            _make_chunk("Introduction: machine learning covers supervised and unsupervised learning.", 0),
            _make_chunk("The algorithm uses entropy as the split criterion for classification.", 1),
            _make_chunk("Random forest is an ensemble variant that combines multiple trees.", 2),
            _make_chunk("Cross-validation is used to evaluate model performance.", 3),
            _make_chunk("The method generalizes well due to low VC dimension.", 4),
            _make_chunk("Regression trees minimize variance reduction at each split.", 5),
        ]
        info = extract_document_topics(chunks)
        # Should detect several topics.
        assert len(info["detected_topics"]) >= 3

    def test_detects_examples_applications(self):
        chunks = [
            _make_chunk("For example, consider a dataset of customer purchases.", 0),
            _make_chunk("This benchmark demonstrates the application of the method.", 1),
        ]
        info = extract_document_topics(chunks)
        assert "examples_applications" in info["detected_topics"]

    def test_no_topics_in_empty_chunks(self):
        info = extract_document_topics([])
        assert info["detected_topics"] == []
        assert info["must_cover_topics"] == []

    def test_single_hit_is_minor(self):
        """A topic with only 1 chunk hit should be minor, not must-cover."""
        chunks = [
            _make_chunk("The algorithm constructs a tree using a recursive procedure.", 0),
        ]
        info = extract_document_topics(chunks, major_topic_min_hits=2)
        if "core_method" in info["detected_topics"]:
            assert "core_method" in info["minor_topics"]
            assert "core_method" not in info["must_cover_topics"]

    def test_outline_text_format(self):
        chunks = [
            _make_chunk("The algorithm partitions data recursively.", 0),
            _make_chunk("The greedy construction procedure selects the best split.", 1),
            _make_chunk("Pruning controls complexity through regularization.", 2),
            _make_chunk("Regularization via cost-complexity pruning removes weak branches.", 3),
        ]
        info = extract_document_topics(chunks)
        outline = info["outline_text"]
        assert "TÓPICOS PRINCIPAIS" in outline or "Nenhum" in outline

    def test_generic_not_hardcoded_to_decision_trees(self):
        """Patterns should work for non-decision-tree ML content."""
        chunks = [
            _make_chunk("The neural network architecture uses backpropagation algorithm for training.", 0),
            _make_chunk("The implementation procedure involves gradient descent optimization.", 1),
            _make_chunk("L2 regularization (weight decay) prevents overfitting.", 2),
            _make_chunk("Dropout regularization randomly deactivates neurons during training.", 3),
            _make_chunk("Cross-validation evaluates the model's generalization ability.", 4),
            _make_chunk("The hyperparameter tuning uses grid search over the learning rate.", 5),
        ]
        info = extract_document_topics(chunks)
        assert "core_method" in info["detected_topics"]
        assert "regularization" in info["detected_topics"]
        assert "validation_tuning" in info["detected_topics"]

    def test_uses_inferred_section_metadata_for_topics(self):
        """Topic extraction should leverage section_title/section_path metadata."""
        chunks = [
            Document(
                page_content="",
                metadata={
                    "chunk_index": 0,
                    "file_type": "pdf",
                    "page": 1,
                    "section_title": "Random Forest Variants",
                    "section_path": "Ensembles > Random Forest",
                },
            ),
            Document(
                page_content="",
                metadata={
                    "chunk_index": 1,
                    "file_type": "pdf",
                    "page": 2,
                    "section_title": "Cross Validation",
                    "section_path": "Evaluation > Cross Validation",
                },
            ),
        ]
        info = extract_document_topics(chunks, major_topic_min_hits=1)
        assert "model_variants" in info["detected_topics"]
        assert "validation_tuning" in info["detected_topics"]

    def test_single_hit_priority_topics_are_must_cover(self):
        """Regularization/validation should be must-cover even with one hit."""
        chunks = [
            _make_chunk("Cost-complexity pruning with alpha_eff controls tree size.", 0),
            _make_chunk("Cross-validation selects the best complexity parameter.", 1),
        ]
        info = extract_document_topics(chunks, major_topic_min_hits=2)
        assert "regularization" in info["must_cover_topics"]
        assert "validation_tuning" in info["must_cover_topics"]


# ── Topic outline coverage scoring tests ──────────────────────────────────────

class TestScoreTopicOutlineCoverage:
    def _make_topic_info(self, must_cover: list[str]) -> dict:
        """Helper to create a topic_info dict with specific must-cover topics."""
        details = {}
        for tid in must_cover:
            details[tid] = {"label": tid.replace("_", " ").title(), "hits": 3, "chunk_indices": [0, 1, 2], "is_major": True}
        return {
            "detected_topics": must_cover,
            "must_cover_topics": must_cover,
            "minor_topics": [],
            "topic_details": details,
        }

    def test_all_topics_covered(self):
        topic_info = self._make_topic_info(["core_method", "regularization"])
        summary = (
            "## Methods\n"
            "The algorithm constructs a decision tree by recursively partitioning the data "
            "using a greedy heuristic at each node. This procedure selects the attribute "
            "that maximizes information gain.\n\n"
            "## Regularization\n"
            "Pruning is used to control overfitting. Cost-complexity pruning removes "
            "branches that do not improve the model's ability to generalize. The regularization "
            "parameter alpha controls the trade-off between tree size and accuracy."
        )
        result = score_topic_outline_coverage(summary, topic_info)
        assert result["overall_score"] >= 0.8
        assert "core_method" in result["covered_topics"]
        assert "regularization" in result["covered_topics"]

    def test_topic_missing_completely(self):
        topic_info = self._make_topic_info(["core_method", "regularization", "generalization_theory"])
        summary = (
            "## Overview\n"
            "The algorithm constructs a classification model using recursive partitioning.\n\n"
            "## Pruning\n"
            "Regularization through pruning controls overfitting by removing weak branches."
        )
        result = score_topic_outline_coverage(summary, topic_info)
        # generalization_theory should be missing.
        assert "generalization_theory" in result["missing_topics"]
        assert result["overall_score"] < 1.0

    def test_topic_mentioned_but_not_explained(self):
        """A topic that appears in a very short context should be weakly covered."""
        topic_info = self._make_topic_info(["core_method", "regularization"])
        summary = (
            "## Methods\n"
            "The algorithm constructs a decision tree by recursively partitioning the data "
            "using a greedy heuristic at each node.\n\n"
            "## Notes\n"
            "Regularization."  # Mentioned but not explained.
        )
        result = score_topic_outline_coverage(summary, topic_info, min_explanation_words=15)
        assert "regularization" not in result["covered_topics"]
        assert result["overall_score"] < 1.0

    def test_no_must_cover_topics(self):
        topic_info = {"detected_topics": [], "must_cover_topics": [], "minor_topics": [], "topic_details": {}}
        result = score_topic_outline_coverage("Some summary text.", topic_info)
        assert result["overall_score"] == 1.0

    def test_false_positive_prevention(self):
        """A fluent summary that name-drops but doesn't explain should score low.

        This is the KEY regression test: previously, a summary could score 1.0
        on all diagnostics while missing major topics.
        """
        topic_info = self._make_topic_info([
            "contextual_framing",
            "core_method",
            "selection_criteria",
            "regularization",
            "generalization_theory",
            "model_variants",
            "regression_formulation",
        ])
        # Fluent but incomplete summary — only covers 2 of 7 topics.
        summary = (
            "## Visão Geral\n"
            "Este documento apresenta uma visão completa sobre árvores de decisão, "
            "um método importante de machine learning supervisionado.\n\n"
            "## Encadeamento e Principais Tópicos\n"
            "O documento discute vários tópicos importantes para o entendimento do modelo.\n\n"
            "## Conceitos Fundamentais\n"
            "A construção do modelo envolve particionar dados usando um algoritmo recursivo "
            "que seleciona o melhor atributo a cada nó interno. O procedimento greedy avalia "
            "cada possível split e escolhe aquele com maior ganho de informação.\n\n"
            "## Aplicações e Variações\n"
            "O modelo pode ser aplicado em diversos cenários.\n\n"
            "## Síntese Final\n"
            "Em resumo, árvores de decisão são ferramentas versáteis que combinam "
            "interpretabilidade com boa performance em problemas de classificação."
        )
        result = score_topic_outline_coverage(summary, topic_info)
        # Should NOT score 1.0 — at least regularization, generalization_theory,
        # model_variants, and regression_formulation are missing.
        assert result["overall_score"] < 0.7, (
            f"Expected low score due to missing topics, got {result['overall_score']:.2f}. "
            f"Missing: {result['missing_topics']}"
        )
        assert len(result["missing_topics"]) >= 3

    def test_long_name_dropping_paragraph_not_full_credit(self):
        """A long paragraph that only lists topics should not get full coverage."""
        topic_info = self._make_topic_info([
            "contextual_framing",
            "taxonomy_classification",
            "core_method",
            "regularization",
        ])
        summary = (
            "O documento menciona introdução, taxonomia, algoritmo principal e regularização, "
            "também aborda avaliação, exemplos e variações, cobrindo os tópicos de forma geral, "
            "mas sem detalhar como cada parte funciona ou se conecta no método."
        )
        result = score_topic_outline_coverage(summary, topic_info, min_explanation_words=15)
        assert result["overall_score"] < 1.0
        assert result["overall_score"] <= 0.6

    def test_complete_summary_scores_high(self):
        """A summary that actually explains all topics should score high."""
        topic_info = self._make_topic_info([
            "core_method",
            "selection_criteria",
            "regularization",
        ])
        summary = (
            "## Methods\n"
            "The algorithm constructs a decision tree by recursively partitioning the training data. "
            "At each internal node, the greedy procedure evaluates all possible splits and selects "
            "the one that maximizes a criterion such as information gain or Gini impurity reduction.\n\n"
            "## Split Criteria\n"
            "The selection of the best split at each node uses entropy-based information gain "
            "or the Gini impurity index. The criterion quantifies the reduction in impurity "
            "achieved by splitting on each candidate attribute.\n\n"
            "## Regularization\n"
            "To prevent overfitting, pruning techniques are applied after tree construction. "
            "Cost-complexity pruning uses an effective alpha parameter to balance tree size "
            "against training accuracy. Cross-validation selects the optimal pruning level."
        )
        result = score_topic_outline_coverage(summary, topic_info)
        assert result["overall_score"] >= 0.8


# ── Topic anchor selection tests ──────────────────────────────────────────────

class TestGetTopicAnchors:
    def test_returns_chunk_indices_per_topic(self):
        chunks = [
            _make_chunk("Regular content.", 0),
            _make_chunk("The algorithm partitions data recursively.", 1),
            _make_chunk("Pruning controls regularization and overfitting.", 2),
        ]
        topic_info = extract_document_topics(chunks)
        anchors = get_topic_anchors(topic_info, chunks)
        # Should have entries for detected topics.
        for topic_id, indices in anchors.items():
            assert all(0 <= i < len(chunks) for i in indices)

    def test_max_per_topic_limit(self):
        chunks = [_make_chunk(f"The algorithm constructs recursively. Chunk {i}.", i) for i in range(10)]
        topic_info = extract_document_topics(chunks)
        anchors = get_topic_anchors(topic_info, chunks, max_per_topic=1)
        for indices in anchors.values():
            assert len(indices) <= 1
