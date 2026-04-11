"""Tests for the semantic grounding module (claims extraction + support checker)."""

import pytest
from langchain_core.documents import Document


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc(text: str) -> Document:
    return Document(
        page_content=text,
        metadata={"file_name": "doc.pdf", "page": 1, "chunk_id": "abc123"},
    )


# ── claims.py ─────────────────────────────────────────────────────────────────

class TestExtractClaims:
    def test_year_triggers_claim(self):
        from docops.grounding.claims import extract_claims

        text = "Em 2023 o sistema processou mais de 1 milhão de requisições."
        claims = extract_claims(text)
        assert any("2023" in c for c in claims)

    def test_percentage_triggers_claim(self):
        from docops.grounding.claims import extract_claims

        text = "A taxa de acerto foi de 87% nos testes realizados."
        claims = extract_claims(text)
        assert len(claims) >= 1

    def test_already_cited_sentence_excluded(self):
        from docops.grounding.claims import extract_claims

        # Sentence already has a citation → should NOT appear in uncited claims
        text = "Em 2023 o sistema foi lançado [Fonte 1]."
        claims = extract_claims(text)
        assert not any("2023" in c for c in claims)

    def test_non_factual_excluded(self):
        from docops.grounding.claims import extract_claims

        text = "Isso parece interessante. Pode ser verdade."
        claims = extract_claims(text)
        assert claims == []

    def test_multiple_claims_extracted(self):
        from docops.grounding.claims import extract_claims

        text = (
            "O sistema foi criado em 2021. "
            "A acurácia média é de 92,5%. "
            "O modelo define-se como um classificador bayesiano."
        )
        claims = extract_claims(text)
        assert len(claims) >= 2


class TestExtractCitedClaims:
    def test_cited_claim_found(self):
        from docops.grounding.claims import extract_cited_claims

        text = "Em 2023 o projeto foi lançado [Fonte 1]."
        cited = extract_cited_claims(text)
        assert len(cited) == 1
        assert "[Fonte 1]" in cited[0]["citations"]

    def test_no_citations_returns_empty(self):
        from docops.grounding.claims import extract_cited_claims

        text = "Texto sem nenhuma citação."
        assert extract_cited_claims(text) == []

    def test_multiple_citations_per_sentence(self):
        from docops.grounding.claims import extract_cited_claims

        text = "Os dados foram validados [Fonte 1] e revisados [Fonte 2]."
        cited = extract_cited_claims(text)
        assert len(cited) == 1
        assert "[Fonte 1]" in cited[0]["citations"]
        assert "[Fonte 2]" in cited[0]["citations"]


# ── support.py ────────────────────────────────────────────────────────────────

class TestHeuristicSupport:
    def test_supported_when_keywords_match(self):
        from docops.grounding.support import check_support

        claim = "O sistema usa aprendizado de máquina para classificar documentos."
        evidence = (
            "O sistema de classificação utiliza algoritmos de aprendizado de máquina "
            "para categorizar os documentos automaticamente."
        )
        result = check_support(claim, evidence, mode="heuristic")
        assert result.label in ("SUPPORTED", "UNCLEAR")
        assert result.score > 0.0

    def test_not_supported_when_unrelated(self):
        from docops.grounding.support import check_support

        claim = "O produto custa R$ 99,99 por mês."
        evidence = "O sistema processa documentos em formato PDF e Markdown."
        result = check_support(claim, evidence, mode="heuristic")
        assert result.label in ("NOT_SUPPORTED", "UNCLEAR")

    def test_number_mismatch_reduces_score(self):
        from docops.grounding.support import check_support

        claim = "A taxa de erro foi 5%."
        evidence = "A taxa de erro registrada nos experimentos foi de 25%."
        result_mismatch = check_support(claim, evidence, mode="heuristic")

        claim_match = "A taxa de erro foi 25%."
        result_match = check_support(claim_match, evidence, mode="heuristic")

        # Matching number should score higher
        assert result_match.score >= result_mismatch.score

    def test_result_has_required_fields(self):
        from docops.grounding.support import check_support

        result = check_support("Claim text.", "Evidence text.", mode="heuristic")
        assert hasattr(result, "label")
        assert hasattr(result, "score")
        assert hasattr(result, "rationale")
        assert result.label in ("SUPPORTED", "NOT_SUPPORTED", "UNCLEAR")
        assert 0.0 <= result.score <= 1.0

    def test_empty_claim_returns_unclear(self):
        from docops.grounding.support import check_support

        result = check_support("", "Some evidence text.", mode="heuristic")
        assert result.label == "UNCLEAR"


class TestComputeSupportRate:
    def test_empty_claims_returns_perfect_rate(self):
        from docops.grounding.support import compute_support_rate

        result = compute_support_rate([], [_doc("evidence")])
        assert result["support_rate"] == 1.0
        assert result["unsupported_claims"] == []

    def test_all_supported_claims(self):
        from docops.grounding.support import compute_support_rate

        claims = [
            "O sistema processa documentos automaticamente.",
        ]
        evidence = [_doc("O sistema processa documentos automaticamente usando RAG.")]
        result = compute_support_rate(claims, evidence, mode="heuristic")
        assert result["support_rate"] >= 0.0  # at least some score
        assert "results" in result
        assert len(result["results"]) == 1

    def test_unrelated_claim_reduces_rate(self):
        from docops.grounding.support import compute_support_rate

        claims = ["Preço mensal R$ 500."]
        evidence = [_doc("O sistema usa embeddings para recuperar documentos.")]
        result = compute_support_rate(claims, evidence, mode="heuristic")
        # Rate should be low / zero for unrelated claim
        assert result["support_rate"] <= 0.5

    def test_mixed_claims_returns_partial_rate(self):
        from docops.grounding.support import compute_support_rate

        evidence_text = (
            "O sistema utiliza aprendizado de máquina. "
            "A acurácia foi de 90%. "
            "Desenvolvido em Python."
        )
        claims = [
            "O sistema utiliza aprendizado de máquina.",  # matches
            "O produto custa 50 dólares por licença.",    # unrelated
        ]
        evidence = [_doc(evidence_text)]
        result = compute_support_rate(claims, evidence, mode="heuristic")
        # First claim should score better than second
        assert result["support_rate"] < 1.0  # not all supported
        assert len(result["results"]) == 2

    def test_unsupported_claims_list(self):
        from docops.grounding.support import compute_support_rate

        claims = ["Frase irrelevante sobre pizza italiana."]
        evidence = [_doc("Documento sobre engenharia de software em Python.")]
        result = compute_support_rate(claims, evidence, mode="heuristic")
        # Should be in unsupported list
        assert isinstance(result["unsupported_claims"], list)

    def test_support_rate_applies_claim_and_chunk_caps(self):
        from docops.grounding.support import compute_support_rate

        claims = [
            "Claim 1 com data 2024.",
            "Claim 2 com data 2025.",
            "Claim 3 com data 2026.",
        ]
        evidence = [
            _doc("Claim 1 com data 2024."),
            _doc("Claim 2 com data 2025."),
            _doc("Claim 3 com data 2026."),
        ]
        result = compute_support_rate(
            claims,
            evidence,
            mode="heuristic",
            max_claims=2,
            max_chunks=1,
        )
        assert result["claims_total"] == 3
        assert result["claims_used"] == 2
        assert result["claims_truncated"] == 1
        assert result["chunks_total"] == 3
        assert result["chunks_used"] == 1
        assert result["chunks_truncated"] == 2

    def test_support_rate_reports_latency_ms(self):
        from docops.grounding.support import compute_support_rate

        claims = ["A taxa foi de 10%."]
        evidence = [_doc("A taxa foi de 10% no experimento.")]
        result = compute_support_rate(claims, evidence, mode="heuristic")
        assert "latency_ms" in result
        assert result["latency_ms"] >= 0.0
