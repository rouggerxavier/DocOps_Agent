"""Testes unitÃ¡rios para eval/benchmark_deep_summary.py.

Cobre:
- agregaÃ§Ã£o estatÃ­stica (percentis, mÃ©dias)
- cÃ¡lculo de accepted_rate
- recomendaÃ§Ã£o automÃ¡tica de perfil
- robustez quando algum run retorna erro / 422
- _extract_run_metrics com payloads mockados
- build_markdown_report e print_terminal_summary
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Importa as funÃ§Ãµes testÃ¡veis (sem dependÃªncias externas de API)
from eval.benchmark_deep_summary import (
    _extract_run_metrics,
    _percentile,
    _mean_notnone,
    _rate,
    _blocking_dist,
    _stage_means,
    aggregate_profile,
    recommend_profile,
    build_markdown_report,
    print_terminal_summary,
    _login,
    _summarize,
    run_benchmark,
)


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _make_ok_body(
    accepted: bool = True,
    weak_ratio: float = 0.05,
    outline_score: float = 0.90,
    rubric_score: float = 0.75,
    inference_density: float = 0.10,
    corrective_passes: int = 0,
    deoverreach_triggered: bool = False,
    deoverreach_accepted: bool = False,
    resynthesis_triggered: bool = False,
    resynthesis_accepted: bool = False,
    total_ms: float = 2000.0,
    blocking_reasons: list[str] | None = None,
) -> dict:
    return {
        "answer": "Resumo de teste.",
        "artifact_path": None,
        "summary_diagnostics": {
            "final": {
                "accepted": accepted,
                "blocking_reasons": blocking_reasons or [],
            },
            "grounding": {"weak_ratio": weak_ratio},
            "outline_coverage": {"score": outline_score},
            "rubric_score": rubric_score,
            "inference_density": {"inference_density": inference_density},
            "corrective_passes_used": corrective_passes,
            "deoverreach": {
                "triggered": deoverreach_triggered,
                "accepted": deoverreach_accepted,
            },
            "resynthesis": {
                "triggered": resynthesis_triggered,
                "accepted": resynthesis_accepted,
            },
            "latency": {
                "total_ms": total_ms,
                "stage_timings_ms": {
                    "collect": 10.0,
                    "partials": 500.0,
                    "consolidate": 300.0,
                    "finalize": 800.0,
                },
            },
        },
    }


def _make_error_body(error: str = "timeout", status_code: int = 0) -> dict:
    return {"error": error, "status_code": status_code}


def _make_422_body(
    blocking_reasons: list[str] | None = None,
    include_status_code: bool = True,
) -> dict:
    body = {
        "detail": {
            "error": "deep_summary_quality_gate_failed",
            "blocking_reasons": blocking_reasons or ["structure_invalid"],
        },
    }
    if include_status_code:
        body["status_code"] = 422
    return body


# â”€â”€ _percentile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestPercentile:
    def test_empty_returns_none(self):
        assert _percentile([], 50) is None

    def test_single_element(self):
        assert _percentile([42.0], 50) == 42.0
        assert _percentile([42.0], 95) == 42.0

    def test_median(self):
        assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0

    def test_p90_five_elements(self):
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        p90 = _percentile(data, 90)
        assert 40.0 <= p90 <= 50.0

    def test_p95_ten_elements(self):
        data = list(range(1, 11, 1))  # 1..10
        p95 = _percentile([float(x) for x in data], 95)
        assert 9.0 <= p95 <= 10.0

    def test_unsorted_input(self):
        assert _percentile([5.0, 1.0, 3.0], 50) == 3.0


# â”€â”€ _mean_notnone â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestMeanNotnone:
    def test_all_none(self):
        assert _mean_notnone([None, None]) is None

    def test_mixed(self):
        result = _mean_notnone([1.0, None, 3.0])
        assert result == pytest.approx(2.0)

    def test_single(self):
        assert _mean_notnone([7.0]) == 7.0

    def test_empty(self):
        assert _mean_notnone([]) is None


# â”€â”€ _rate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestRate:
    def test_all_true(self):
        assert _rate([True, True, True]) == 1.0

    def test_all_false(self):
        assert _rate([False, False]) == 0.0

    def test_mixed(self):
        assert _rate([True, False, True, False]) == pytest.approx(0.5)

    def test_all_none(self):
        assert _rate([None, None]) is None

    def test_empty(self):
        assert _rate([]) is None

    def test_none_ignored(self):
        assert _rate([True, None, True]) == 1.0


# â”€â”€ _extract_run_metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestExtractRunMetrics:
    def test_ok_body_accepted(self):
        body = _make_ok_body(accepted=True, corrective_passes=0)
        m = _extract_run_metrics(body, wall_ms=1500.0)
        assert m["accepted"] is True
        assert m["wall_ms"] == 1500.0
        assert m["error"] is None
        assert m["corrective_passes_used"] == 0
        assert m["weak_ratio"] == pytest.approx(0.05)
        assert m["outline_coverage_score"] == pytest.approx(0.90)
        assert m["rubric_score"] == pytest.approx(0.75)
        assert m["inference_density"] == pytest.approx(0.10)
        assert m["internal_total_ms"] == pytest.approx(2000.0)
        assert "collect" in m["stage_timings_ms"]

    def test_ok_body_not_accepted(self):
        body = _make_ok_body(accepted=False, blocking_reasons=["structure_invalid"])
        m = _extract_run_metrics(body, wall_ms=2000.0)
        assert m["accepted"] is False
        assert "structure_invalid" in m["blocking_reasons"]

    def test_error_body(self):
        body = _make_error_body("timeout", 0)
        m = _extract_run_metrics(body, wall_ms=30000.0)
        assert m["error"] == "timeout"
        assert m["accepted"] is False
        assert m["wall_ms"] == 30000.0
        assert m["blocking_reasons"] == []

    def test_422_body_strict_fail_closed(self):
        body = _make_422_body(["inference_density_exceeded"])
        m = _extract_run_metrics(body, wall_ms=3000.0)
        assert m["status_code"] == 422
        assert m["accepted"] is False
        assert m["error"] == "strict_fail_closed_422"
        assert "inference_density_exceeded" in m["blocking_reasons"]

    def test_422_body_without_status_code_is_detected(self):
        body = _make_422_body(["structure_invalid"], include_status_code=False)
        m = _extract_run_metrics(body, wall_ms=3000.0)
        assert m["status_code"] == 422
        assert m["accepted"] is False
        assert m["error"] == "strict_fail_closed_422"
        assert "structure_invalid" in m["blocking_reasons"]

    def test_rubric_score_zero_is_preserved(self):
        body = _make_ok_body(rubric_score=0.75)
        body["summary_diagnostics"]["rubric"] = {"overall_score": 0.0}
        body["summary_diagnostics"]["rubric_score"] = 0.91
        m = _extract_run_metrics(body, wall_ms=1000.0)
        assert m["rubric_score"] == 0.0

    def test_deoverreach_fields(self):
        body = _make_ok_body(deoverreach_triggered=True, deoverreach_accepted=False)
        m = _extract_run_metrics(body, wall_ms=1000.0)
        assert m["deoverreach_triggered"] is True
        assert m["deoverreach_accepted"] is False

    def test_resynthesis_fields(self):
        body = _make_ok_body(resynthesis_triggered=True, resynthesis_accepted=True)
        m = _extract_run_metrics(body, wall_ms=1000.0)
        assert m["resynthesis_triggered"] is True
        assert m["resynthesis_accepted"] is True

    def test_missing_diagnostics_gracefully(self):
        body = {"answer": "ok", "artifact_path": None, "summary_diagnostics": None}
        # No diagnostics â†’ treats as error-less but empty
        m = _extract_run_metrics(body, wall_ms=500.0)
        assert m["wall_ms"] == 500.0


# â”€â”€ _blocking_dist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestBlockingDist:
    def test_counts_correctly(self):
        runs = [
            {"blocking_reasons": ["a", "b"]},
            {"blocking_reasons": ["a"]},
            {"blocking_reasons": []},
        ]
        dist = _blocking_dist(runs)
        assert dist["a"] == 2
        assert dist["b"] == 1

    def test_empty_runs(self):
        assert _blocking_dist([]) == {}

    def test_none_blocking_reasons(self):
        runs = [{"blocking_reasons": None}]
        assert _blocking_dist(runs) == {}


# â”€â”€ _stage_means â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestStageMeans:
    def test_averages_correctly(self):
        runs = [
            {"stage_timings_ms": {"collect": 10.0, "finalize": 100.0}},
            {"stage_timings_ms": {"collect": 20.0, "finalize": 200.0}},
        ]
        means = _stage_means(runs)
        assert means["collect"] == pytest.approx(15.0)
        assert means["finalize"] == pytest.approx(150.0)

    def test_missing_stage_in_some_runs(self):
        runs = [
            {"stage_timings_ms": {"collect": 10.0}},
            {"stage_timings_ms": {}},
        ]
        means = _stage_means(runs)
        assert means["collect"] == pytest.approx(10.0)

    def test_empty_runs(self):
        assert _stage_means([]) == {}


# â”€â”€ aggregate_profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestAggregateProfile:
    def _make_run(self, accepted: bool = True, wall_ms: float = 1000.0) -> dict:
        body = _make_ok_body(accepted=accepted)
        m = _extract_run_metrics(body, wall_ms)
        return m

    def test_basic_aggregate(self):
        runs = [self._make_run(accepted=True, wall_ms=float(ms)) for ms in [1000, 1200, 1100]]
        agg = aggregate_profile("model_first", runs)
        assert agg["profile"] == "model_first"
        assert agg["n_runs"] == 3
        assert agg["n_errors"] == 0
        assert agg["quality"]["accepted_rate"] == pytest.approx(1.0)
        assert agg["latency"]["min_ms"] == pytest.approx(1000.0)
        assert agg["latency"]["max_ms"] == pytest.approx(1200.0)

    def test_error_runs_excluded_from_latency(self):
        good = self._make_run(wall_ms=1000.0)
        err = _extract_run_metrics(_make_error_body(), wall_ms=500.0)
        agg = aggregate_profile("fast", [good, err])
        assert agg["n_errors"] == 1
        # error run's 500ms wall should be excluded from latency calc
        assert agg["latency"]["mean_ms"] == pytest.approx(1000.0)

    def test_partial_accepted_rate(self):
        runs = [
            self._make_run(accepted=True),
            self._make_run(accepted=False),
            self._make_run(accepted=True),
            self._make_run(accepted=False),
        ]
        agg = aggregate_profile("strict", runs)
        assert agg["quality"]["accepted_rate"] == pytest.approx(0.5)

    def test_corrective_pass_mean(self):
        def _run_with_passes(n: int) -> dict:
            body = _make_ok_body(corrective_passes=n)
            return _extract_run_metrics(body, 1000.0)

        runs = [_run_with_passes(0), _run_with_passes(1), _run_with_passes(1)]
        agg = aggregate_profile("model_first", runs)
        assert agg["corrective"]["mean_passes_used"] == pytest.approx(2 / 3, abs=1e-3)

    def test_all_errors_latency_none(self):
        runs = [_extract_run_metrics(_make_error_body(), 1.0) for _ in range(3)]
        agg = aggregate_profile("fast", runs)
        assert agg["latency"]["mean_ms"] is None
        assert agg["n_errors"] == 3


# â”€â”€ recommend_profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestRecommendProfile:
    def _agg(self, profile: str, accepted_rate: float, p95: float) -> dict:
        return {
            "profile": profile,
            "quality": {"accepted_rate": accepted_rate},
            "latency": {"p95_ms": p95},
        }

    def test_selects_lowest_p95_among_qualified(self):
        aggs = [
            self._agg("fast", 0.9, 2000.0),
            self._agg("model_first", 0.85, 3000.0),
            self._agg("strict", 0.95, 5000.0),
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        assert rec["recommended_profile"] == "fast"
        assert rec["risk"] is False

    def test_risk_flag_when_none_qualify(self):
        aggs = [
            self._agg("fast", 0.5, 1000.0),
            self._agg("model_first", 0.6, 2000.0),
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        assert rec["risk"] is True
        assert rec["risk_message"] is not None
        # should still recommend one
        assert rec["recommended_profile"] in ("fast", "model_first")

    def test_risk_selects_highest_accepted_rate(self):
        aggs = [
            self._agg("fast", 0.4, 1000.0),
            self._agg("model_first", 0.7, 2000.0),
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        assert rec["risk"] is True
        assert rec["recommended_profile"] == "model_first"

    def test_single_profile(self):
        aggs = [self._agg("model_first", 1.0, 1500.0)]
        rec = recommend_profile(aggs, threshold=0.8)
        assert rec["recommended_profile"] == "model_first"
        assert rec["risk"] is False

    def test_tie_broken_by_lower_p95(self):
        aggs = [
            self._agg("model_first", 0.9, 3000.0),
            self._agg("strict", 0.9, 2000.0),
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        assert rec["recommended_profile"] == "strict"

    def test_threshold_boundary(self):
        aggs = [
            self._agg("fast", 0.8, 1000.0),     # exactly at threshold
            self._agg("model_first", 0.79, 500.0), # just below
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        assert rec["recommended_profile"] == "fast"
        assert rec["risk"] is False

    def test_qualified_profiles_listed(self):
        aggs = [
            self._agg("fast", 0.9, 1000.0),
            self._agg("model_first", 0.85, 2000.0),
            self._agg("strict", 0.5, 500.0),  # too low accepted_rate
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        assert "fast" in rec["qualified_profiles"]
        assert "model_first" in rec["qualified_profiles"]
        assert "strict" not in rec["qualified_profiles"]


# â”€â”€ build_markdown_report â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestBuildMarkdownReport:
    def _sample_aggregates(self) -> list[dict]:
        aggs = []
        for profile, p95, ar in [("fast", 1000.0, 0.9), ("model_first", 2000.0, 0.95)]:
            runs = [
                _extract_run_metrics(_make_ok_body(accepted=(i < 9)), 1000.0)
                for i in range(10)
            ]
            agg = aggregate_profile(profile, runs)
            # override p95 for predictability
            agg["latency"]["p95_ms"] = p95
            agg["quality"]["accepted_rate"] = ar
            aggs.append(agg)
        return aggs

    def test_report_contains_sections(self):
        aggs = self._sample_aggregates()
        rec = recommend_profile(aggs)
        meta = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "doc": "test.pdf",
            "runs_per_profile": 10,
            "warmup_runs": 1,
            "base_url": "http://localhost:8000",
        }
        md = build_markdown_report("test.pdf", aggs, rec, meta)
        assert "# Benchmark Deep Summary" in md
        assert "Latência" in md
        assert "Qualidade" in md
        assert "Custo Corretivo" in md
        assert "Recomendação" in md

    def test_report_contains_profile_names(self):
        aggs = self._sample_aggregates()
        rec = recommend_profile(aggs)
        meta = {"timestamp": "", "doc": "t.pdf", "runs_per_profile": 10,
                "warmup_runs": 1, "base_url": ""}
        md = build_markdown_report("t.pdf", aggs, rec, meta)
        assert "fast" in md
        assert "model_first" in md

    def test_report_contains_recommended_profile(self):
        aggs = self._sample_aggregates()
        rec = recommend_profile(aggs)
        meta = {"timestamp": "", "doc": "t.pdf", "runs_per_profile": 10,
                "warmup_runs": 1, "base_url": ""}
        md = build_markdown_report("t.pdf", aggs, rec, meta)
        assert rec["recommended_profile"] in md

    def test_risk_flag_in_report(self):
        aggs = [
            aggregate_profile("fast", [
                _extract_run_metrics(_make_ok_body(accepted=False), 1000.0)
                for _ in range(3)
            ])
        ]
        rec = recommend_profile(aggs, threshold=0.8)
        meta = {"timestamp": "", "doc": "t.pdf", "runs_per_profile": 3,
                "warmup_runs": 0, "base_url": ""}
        md = build_markdown_report("t.pdf", aggs, rec, meta)
        assert "RISCO" in md or "risk" in md.lower()


# â”€â”€ print_terminal_summary (smoke) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestPrintTerminalSummary:
    def test_prints_without_error(self, capsys):
        aggs = [
            aggregate_profile("fast", [
                _extract_run_metrics(_make_ok_body(accepted=True), 1000.0)
                for _ in range(3)
            ])
        ]
        rec = recommend_profile(aggs)
        print_terminal_summary(aggs, rec)
        captured = capsys.readouterr()
        assert "BENCHMARK" in captured.out
        assert "fast" in captured.out


# â”€â”€ HTTP layer (mocked) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestLoginMocked:
    def test_login_returns_token(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok123", "token_type": "bearer"}
        mock_resp.raise_for_status = MagicMock()

        with patch("eval.benchmark_deep_summary.requests.post", return_value=mock_resp):
            token = _login("http://localhost:8000", "a@b.com", "pass")

        assert token == "tok123"

    def test_login_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch("eval.benchmark_deep_summary.requests.post", return_value=mock_resp):
            with pytest.raises(Exception, match="401"):
                _login("http://localhost:8000", "a@b.com", "wrong")


class TestSummarizeMocked:
    def test_returns_body_and_elapsed(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_ok_body()

        with patch("eval.benchmark_deep_summary.requests.post", return_value=mock_resp):
            body, ms = _summarize("http://localhost:8000", "tok", "doc.pdf", "fast")

        assert body["answer"] == "Resumo de teste."
        assert ms >= 0.0

    def test_422_returned_as_body(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = _make_422_body(
            ["structure_invalid"],
            include_status_code=False,
        )

        with patch("eval.benchmark_deep_summary.requests.post", return_value=mock_resp):
            body, ms = _summarize("http://localhost:8000", "tok", "doc.pdf", "strict")

        assert body["detail"]["blocking_reasons"] == ["structure_invalid"]
        assert body["status_code"] == 422

    def test_http_500_returns_error_dict(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("eval.benchmark_deep_summary.requests.post", return_value=mock_resp):
            body, ms = _summarize("http://localhost:8000", "tok", "doc.pdf", "fast")

        assert body["error"] == "Internal Server Error"
        assert body["status_code"] == 500

    def test_timeout_returns_error_dict(self):
        import requests as req_lib

        with patch("eval.benchmark_deep_summary.requests.post",
                   side_effect=req_lib.Timeout()):
            body, ms = _summarize("http://localhost:8000", "tok", "doc.pdf", "fast")

        assert body["error"] == "timeout"
        assert body["status_code"] == 0


# â”€â”€ run_benchmark integration (fully mocked) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestRunBenchmarkMocked:
    """End-to-end test of run_benchmark using mocked HTTP calls."""

    def _mock_login(self, *a, **kw):
        return "mock-token"

    def _mock_summarize(self, *a, **kw):
        return _make_ok_body(accepted=True), 1200.0

    def test_run_benchmark_produces_json_and_md(self, tmp_path):
        out_json = tmp_path / "bench.json"
        out_md = tmp_path / "bench.md"

        with (
            patch("eval.benchmark_deep_summary._login", self._mock_login),
            patch("eval.benchmark_deep_summary._summarize", self._mock_summarize),
        ):
            report = run_benchmark(
                doc="doc.pdf",
                profiles=["fast", "model_first"],
                runs=3,
                warmup=0,
                base_url="http://localhost:8000",
                email="a@b.com",
                password="pass",
                out_json=out_json,
                out_md=out_md,
                accepted_threshold=0.95,
            )

        assert out_json.exists()
        assert out_md.exists()
        data = json.loads(out_json.read_text())
        assert "aggregates" in data
        assert "recommendation" in data
        assert len(data["aggregates"]) == 2
        assert data["recommendation"]["accepted_rate_threshold"] == pytest.approx(0.95)
        assert data["meta"]["accepted_threshold"] == pytest.approx(0.95)

    def test_run_benchmark_handles_all_errors(self, tmp_path):
        out_json = tmp_path / "bench_err.json"
        out_md = tmp_path / "bench_err.md"

        def _mock_summarize_err(*a, **kw):
            return _make_error_body("timeout"), 30000.0

        with (
            patch("eval.benchmark_deep_summary._login", self._mock_login),
            patch("eval.benchmark_deep_summary._summarize", _mock_summarize_err),
        ):
            report = run_benchmark(
                doc="doc.pdf",
                profiles=["fast"],
                runs=3,
                warmup=0,
                base_url="http://localhost:8000",
                email="a@b.com",
                password="pass",
                out_json=out_json,
                out_md=out_md,
            )

        agg = report["aggregates"][0]
        assert agg["n_errors"] == 3
        assert agg["quality"]["accepted_rate"] == 0.0
        assert "NaN" not in out_json.read_text(encoding="utf-8")

    def test_run_benchmark_422_counted_as_not_accepted(self, tmp_path):
        out_json = tmp_path / "bench_422.json"
        out_md = tmp_path / "bench_422.md"

        def _mock_summarize_422(*a, **kw):
            return _make_422_body(["structure_invalid"]), 2000.0

        with (
            patch("eval.benchmark_deep_summary._login", self._mock_login),
            patch("eval.benchmark_deep_summary._summarize", _mock_summarize_422),
        ):
            report = run_benchmark(
                doc="doc.pdf",
                profiles=["strict"],
                runs=3,
                warmup=0,
                base_url="http://localhost:8000",
                email="a@b.com",
                password="pass",
                out_json=out_json,
                out_md=out_md,
            )

        agg = report["aggregates"][0]
        # 422 accepted=False but NOT counted as error (still a valid HTTP response)
        assert agg["quality"]["accepted_rate"] == 0.0

