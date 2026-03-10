"""Tests for the eval harness (suite parsing, metrics, runner with mock agent)."""

import json
import tempfile
from pathlib import Path

import pytest
from langchain_core.documents import Document


# ── Suite parsing ─────────────────────────────────────────────────────────────

DEMO_YAML = """\
suite_name: test_suite
description: Suite de teste unitário
corpus: []
cases:
  - id: case_01
    question: "Qual é a taxa de acerto em 2023?"
    expected: null
    must_cite: []
    tags: [factual, numbers]

  - id: case_02
    question: "Faça um resumo do documento."
    expected: null
    must_cite: []
    tags: [summary]

  - id: case_abstain
    question: "Qual é o preço do produto?"
    expected: ""
    must_cite: []
    tags: [abstain]

  - id: case_expected_list
    question: "Defina RAG."
    expected:
      - "retrieval"
      - "generation"
    must_cite: []
    tags: [factual]
"""


def _write_suite(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "suite.yaml"
    p.write_text(content, encoding="utf-8")
    return p


class TestLoadSuite:
    def test_parses_suite_name(self, tmp_path):
        from eval.runner import load_suite

        p = _write_suite(tmp_path, DEMO_YAML)
        suite = load_suite(p)
        assert suite.suite_name == "test_suite"

    def test_parses_cases(self, tmp_path):
        from eval.runner import load_suite

        p = _write_suite(tmp_path, DEMO_YAML)
        suite = load_suite(p)
        assert len(suite.cases) == 4

    def test_case_fields(self, tmp_path):
        from eval.runner import load_suite

        p = _write_suite(tmp_path, DEMO_YAML)
        suite = load_suite(p)
        c = suite.cases[0]
        assert c.id == "case_01"
        assert "factual" in c.tags
        assert c.expected is None

    def test_expected_can_be_list(self, tmp_path):
        from eval.runner import load_suite

        p = _write_suite(tmp_path, DEMO_YAML)
        suite = load_suite(p)
        c = next(x for x in suite.cases if x.id == "case_expected_list")
        assert isinstance(c.expected, list)
        assert "retrieval" in c.expected

    def test_abstain_case_expected_empty_string(self, tmp_path):
        from eval.runner import load_suite

        p = _write_suite(tmp_path, DEMO_YAML)
        suite = load_suite(p)
        abstain = next(c for c in suite.cases if c.id == "case_abstain")
        assert abstain.expected == ""

    def test_missing_file_raises(self):
        from eval.runner import load_suite

        with pytest.raises(FileNotFoundError):
            load_suite("/nonexistent/path/suite.yaml")


# ── Metrics ───────────────────────────────────────────────────────────────────

class TestCitationCoverage:
    def test_factual_with_citation_full_coverage(self):
        from eval.runner import citation_coverage

        answer = "Em 2023 o sistema processou 1 milhão de requisições [Fonte 1]."
        assert citation_coverage(answer) == 1.0

    def test_factual_without_citation_zero_coverage(self):
        from eval.runner import citation_coverage

        answer = "Em 2023 o sistema processou 1 milhão de requisições."
        cov = citation_coverage(answer)
        assert cov < 1.0

    def test_no_factual_sentences_returns_one(self):
        from eval.runner import citation_coverage

        answer = "Parece ser uma boa ideia."
        assert citation_coverage(answer) == 1.0


class TestIsAbstention:
    def test_abstain_phrase_detected(self):
        from eval.runner import is_abstention

        answer = "Não encontrei informação suficiente nos documentos."
        assert is_abstention(answer) is True

    def test_normal_answer_not_abstention(self):
        from eval.runner import is_abstention

        answer = "O sistema foi criado em 2021 conforme descrito."
        assert is_abstention(answer) is False


class TestRetrievalRecallProxy:
    def test_keywords_present_returns_high_recall(self):
        from eval.runner import retrieval_recall_proxy

        question = "Como funciona o retrieval híbrido?"
        chunks = [
            Document(
                page_content="O retrieval híbrido combina busca lexical e vetorial.",
                metadata={},
            )
        ]
        recall = retrieval_recall_proxy(question, chunks)
        assert recall > 0.0

    def test_no_chunks_returns_valid_score(self):
        from eval.runner import retrieval_recall_proxy

        recall = retrieval_recall_proxy("Pergunta qualquer?", [])
        assert 0.0 <= recall <= 1.0


class TestMustCitePass:
    def test_pattern_present_passes(self):
        from eval.runner import must_cite_pass

        answer = "O documento menciona o arquivo config.yaml com detalhes."
        assert must_cite_pass(answer, ["config.yaml"]) is True

    def test_pattern_absent_fails(self):
        from eval.runner import must_cite_pass

        answer = "O sistema usa embeddings para recuperação."
        assert must_cite_pass(answer, ["config.yaml"]) is False

    def test_empty_must_cite_always_passes(self):
        from eval.runner import must_cite_pass

        assert must_cite_pass("qualquer resposta", []) is True


# ── Runner with mock agent ────────────────────────────────────────────────────

class TestEvalRunner:
    def _mock_agent(self, question: str) -> dict:
        """Stub: returns abstention for questions about price, otherwise generic answer."""
        if "preço" in question.lower() or "price" in question.lower():
            return {
                "answer": "Não encontrei informação sobre preço nos documentos.",
                "retrieved_chunks": [],
            }
        return {
            "answer": "Em 2023 [Fonte 1] o sistema processou requisições com 90% de acurácia [Fonte 2].",
            "retrieved_chunks": [
                Document(
                    page_content="Em 2023 o sistema processou requisições com alta acurácia.",
                    metadata={"file_name": "doc.pdf", "page": 1, "chunk_id": "aaa"},
                )
            ],
        }

    def test_runner_completes_without_error(self, tmp_path):
        from eval.runner import EvalRunner

        p = _write_suite(tmp_path, DEMO_YAML)
        runner = EvalRunner(suite_path=p, agent_fn=self._mock_agent)
        report = runner.run()
        assert report.suite_name == "test_suite"
        assert len(report.cases) == 4

    def test_summary_has_required_keys(self, tmp_path):
        from eval.runner import EvalRunner

        p = _write_suite(tmp_path, DEMO_YAML)
        runner = EvalRunner(suite_path=p, agent_fn=self._mock_agent)
        report = runner.run()
        required_keys = {
            "total_cases", "errors",
            "avg_citation_coverage", "avg_citation_support_rate",
            "abstention_accuracy", "avg_retrieval_recall_proxy",
            "must_cite_pass_rate",
        }
        assert required_keys.issubset(report.summary.keys())

    def test_abstain_case_detected(self, tmp_path):
        from eval.runner import EvalRunner

        p = _write_suite(tmp_path, DEMO_YAML)
        runner = EvalRunner(suite_path=p, agent_fn=self._mock_agent)
        report = runner.run()

        abstain_case = next(r for r in report.cases if r.case_id == "case_abstain")
        assert abstain_case.expected_abstention is True
        assert abstain_case.is_abstention is True
        assert abstain_case.abstention_correct is True

    def test_max_cases_limits_run(self, tmp_path):
        from eval.runner import EvalRunner

        p = _write_suite(tmp_path, DEMO_YAML)
        runner = EvalRunner(suite_path=p, agent_fn=self._mock_agent, max_cases=1)
        report = runner.run()
        assert len(report.cases) == 1

    def test_save_writes_json(self, tmp_path):
        from eval.runner import EvalRunner

        p = _write_suite(tmp_path, DEMO_YAML)
        runner = EvalRunner(suite_path=p, agent_fn=self._mock_agent)
        report = runner.run()

        out_path = tmp_path / "report.json"
        runner.save(report, out_path)
        assert out_path.exists()

        with open(out_path, encoding="utf-8") as fh:
            data = json.load(fh)

        assert data["suite_name"] == "test_suite"
        assert "summary" in data
        assert "cases" in data

    def test_case_error_does_not_crash_runner(self, tmp_path):
        from eval.runner import EvalRunner

        def _failing_agent(question: str) -> dict:
            raise RuntimeError("Simulated pipeline failure")

        p = _write_suite(tmp_path, DEMO_YAML)
        runner = EvalRunner(suite_path=p, agent_fn=_failing_agent)
        report = runner.run()

        # All cases should have errors, but runner should still complete
        assert all(r.error is not None for r in report.cases)
        assert report.summary["errors"] == 4


DEEP_SUMMARY_SUITE_YAML = """\
suite_name: deep_summary_regression_test
description: test suite
thresholds:
  require_structure_valid: true
  min_coverage_score: 0.30
  max_weak_grounding_ratio: 1.00
  min_unique_sources: 1
cases:
  - id: ds_ok
    doc_name: doc_formula.pdf
    chunk_texts:
      - "A equação usa α e β para modelagem."
      - "Passo 1: preparar dados."
    summary_text: |
      ## Panorama Geral
      O texto apresenta a equação base [Fonte 1].

      ## Linha Lógica
      O procedimento de cálculo segue etapas simples [Fonte 2].

      ## Conceitos Centrais
      O conceito de parametrização é definido no material [Fonte 1].

      ## Síntese Final
      A conclusão integra fórmula e execução prática [Fonte 2].
  - id: ds_fail
    doc_name: doc_fail.pdf
    chunk_texts:
      - "Conteúdo sem estrutura."
    summary_text: "Resumo sem headings e sem fontes."
"""


class TestDeepSummaryRegressionRunner:
    def test_runner_detects_pass_and_fail(self, tmp_path):
        from eval.deep_summary_runner import DeepSummaryRegressionRunner

        suite_path = _write_suite(tmp_path, DEEP_SUMMARY_SUITE_YAML)
        runner = DeepSummaryRegressionRunner(suite_path=suite_path)
        report = runner.run()

        assert report.suite_name == "deep_summary_regression_test"
        assert len(report.cases) == 2
        assert report.summary["failed_cases"] >= 1

    def test_runner_save_writes_json(self, tmp_path):
        from eval.deep_summary_runner import DeepSummaryRegressionRunner

        suite_path = _write_suite(tmp_path, DEEP_SUMMARY_SUITE_YAML)
        runner = DeepSummaryRegressionRunner(suite_path=suite_path)
        report = runner.run()
        out_path = tmp_path / "deep_summary_report.json"
        saved = runner.save(report, out_path)

        assert saved.exists()
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data["suite_name"] == "deep_summary_regression_test"
        assert "summary" in data
