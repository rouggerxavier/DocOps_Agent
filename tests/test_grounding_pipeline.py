"""Integration-style tests for grounding verifier behavior in graph nodes."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.documents import Document

from docops.graph.nodes import verify_grounding_node


def _state() -> dict:
    return {
        "query": "Qual foi o resultado?",
        "answer": "Resposta original sem suporte suficiente.",
        "raw_answer": "Resposta original sem suporte suficiente.",
        "context_block": "[Fonte 1] doc.md\ntexto",
        "retrieved_chunks": [
            Document(page_content="Trecho de evidencia.", metadata={"file_name": "doc.md", "page": 1})
        ],
        "retry_count": 0,
        "repair_count": 0,
    }


def test_repair_pass_applied_when_support_is_low_then_recovers():
    state = _state()

    with (
        patch("docops.graph.nodes.verify_grounding") as mock_verify,
        patch("docops.graph.nodes._semantic_grounding_payload") as mock_sem,
        patch("docops.graph.nodes._repair_answer", return_value="Resposta reparada [Fonte 1]."),
        patch("docops.graph.nodes.config") as mock_cfg,
    ):
        mock_verify.return_value = {"grounding_ok": True, "retry": False, "disclaimer": ""}
        mock_sem.side_effect = [
            {"support_rate": 0.2, "unsupported_claims": ["claim x"], "claims_checked": 1},
            {"support_rate": 0.95, "unsupported_claims": [], "claims_checked": 1},
        ]
        mock_cfg.semantic_grounding_enabled = True
        mock_cfg.min_support_rate = 0.8
        mock_cfg.grounded_verifier_mode = "heuristic"
        mock_cfg.grounding_repair_max_passes = 1
        mock_cfg.grounding_retrieval_max_retries = 1

        result = verify_grounding_node(state)  # type: ignore[arg-type]

    assert result["answer"] == "Resposta reparada [Fonte 1]."
    assert result["repair_count"] == 1
    assert result["retry"] is False
    assert result["grounding_ok"] is True


def test_retrieval_retry_triggered_when_support_stays_low():
    state = _state()

    with (
        patch("docops.graph.nodes.verify_grounding") as mock_verify,
        patch("docops.graph.nodes._semantic_grounding_payload") as mock_sem,
        patch("docops.graph.nodes._repair_answer", return_value="Resposta ainda ruim."),
        patch("docops.graph.nodes.config") as mock_cfg,
    ):
        mock_verify.return_value = {"grounding_ok": True, "retry": False, "disclaimer": ""}
        mock_sem.return_value = {
            "support_rate": 0.1,
            "unsupported_claims": ["claim x"],
            "claims_checked": 1,
        }
        mock_cfg.semantic_grounding_enabled = True
        mock_cfg.min_support_rate = 0.8
        mock_cfg.grounded_verifier_mode = "heuristic"
        mock_cfg.grounding_repair_max_passes = 1
        mock_cfg.grounding_retrieval_max_retries = 1

        result = verify_grounding_node(state)  # type: ignore[arg-type]

    assert result["retry"] is True
    assert result["grounding_ok"] is False


def test_low_support_without_retry_budget_adds_disclaimer():
    state = _state()
    state["retry_count"] = 2
    state["repair_count"] = 1

    with (
        patch("docops.graph.nodes.verify_grounding") as mock_verify,
        patch("docops.graph.nodes._semantic_grounding_payload") as mock_sem,
        patch("docops.graph.nodes.config") as mock_cfg,
    ):
        mock_verify.return_value = {"grounding_ok": True, "retry": False, "disclaimer": ""}
        mock_sem.return_value = {
            "support_rate": 0.1,
            "unsupported_claims": ["claim x"],
            "claims_checked": 1,
        }
        mock_cfg.semantic_grounding_enabled = True
        mock_cfg.min_support_rate = 0.8
        mock_cfg.grounded_verifier_mode = "heuristic"
        mock_cfg.grounding_repair_max_passes = 1
        mock_cfg.grounding_retrieval_max_retries = 1

        result = verify_grounding_node(state)  # type: ignore[arg-type]

    assert result["retry"] is False
    assert result["grounding_ok"] is False
    assert "Aviso" in result.get("disclaimer", "")
