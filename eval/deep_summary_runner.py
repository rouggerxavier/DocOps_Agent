"""Offline regression runner for deep-summary quality gates."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from docops.config import config
from docops.summarize.outline import (
    extract_document_topics,
    score_topic_outline_coverage,
)
from docops.summarize.coverage_profiles import resolve_coverage_profile
from docops.summarize.pipeline import (
    check_formula_mode,
    classify_claim_risks,
    compute_inference_density,
    detect_coverage_signals,
    score_coverage,
    validate_summary_grounding,
    validate_summary_structure,
)

_CITATION_RE = re.compile(r"\[Fonte\s*(\d+)\]", re.IGNORECASE)


@dataclass
class DeepSummaryEvalCase:
    id: str
    doc_name: str
    chunk_texts: list[str] = field(default_factory=list)
    summary_text: str = ""
    description: str = ""
    thresholds: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeepSummaryEvalSuite:
    suite_name: str
    description: str = ""
    thresholds: dict[str, Any] = field(default_factory=dict)
    cases: list[DeepSummaryEvalCase] = field(default_factory=list)


@dataclass
class DeepSummaryCaseResult:
    case_id: str
    doc_name: str
    passed: bool
    structure_valid: bool
    coverage_score: float
    outline_coverage_score: float
    weak_grounding_ratio: float
    unique_sources_used: int
    profile_name: str
    thresholds: dict[str, Any]
    unsupported_high_risk_count: int = 0
    formula_claims_downgraded_to_concept: int = 0
    inference_density: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class DeepSummaryEvalReport:
    suite_name: str
    run_at: str
    settings: dict[str, Any]
    summary: dict[str, Any]
    cases: list[DeepSummaryCaseResult]


def load_deep_summary_suite(path: str | Path) -> DeepSummaryEvalSuite:
    """Load deep-summary regression suite from YAML."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pyyaml is required for deep-summary suites: pip install pyyaml") from exc

    suite_path = Path(path)
    with suite_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    cases = [
        DeepSummaryEvalCase(
            id=str(item["id"]),
            doc_name=str(item["doc_name"]),
            chunk_texts=list(item.get("chunk_texts") or []),
            summary_text=str(item.get("summary_text") or ""),
            description=str(item.get("description") or ""),
            thresholds=dict(item.get("thresholds") or {}),
        )
        for item in list(raw.get("cases") or [])
    ]
    return DeepSummaryEvalSuite(
        suite_name=str(raw.get("suite_name") or "deep_summary_regression"),
        description=str(raw.get("description") or ""),
        thresholds=dict(raw.get("thresholds") or {}),
        cases=cases,
    )


class DeepSummaryRegressionRunner:
    """Run deterministic deep-summary regression checks over fixed corpus cases."""

    def __init__(self, suite_path: str | Path) -> None:
        self.suite_path = Path(suite_path)
        self.suite = load_deep_summary_suite(self.suite_path)

    def _make_chunks(self, case: DeepSummaryEvalCase) -> list[Document]:
        chunks: list[Document] = []
        for i, text in enumerate(case.chunk_texts):
            chunks.append(
                Document(
                    page_content=text,
                    metadata={
                        "chunk_index": i,
                        "file_name": case.doc_name,
                        "page": i + 1,
                        "page_start": i + 1,
                        "page_end": i + 1,
                    },
                )
            )
        return chunks

    def _merge_thresholds(self, case: DeepSummaryEvalCase) -> dict[str, Any]:
        base = {
            "require_structure_valid": True,
            "min_coverage_score": 0.50,
            "max_weak_grounding_ratio": 0.50,
            "min_unique_sources": 2,
            "structure_min_chars": 40,
            # Optional by default; enforced only when provided by suite/case.
            "min_outline_coverage_score": None,
            "max_outline_coverage_score": None,
            "min_unsupported_high_risk_count": None,
            "max_unsupported_high_risk_count": None,
            "min_formula_claims_downgraded": None,
            "max_formula_claims_downgraded": None,
            "min_inference_density": None,
            "max_inference_density": None,
            "formula_mode": None,
        }
        base.update(self.suite.thresholds or {})
        base.update(case.thresholds or {})
        return base

    def _count_unique_sources(self, text: str, n_anchors: int) -> int:
        used = {
            int(m)
            for m in _CITATION_RE.findall(text or "")
            if 1 <= int(m) <= max(0, n_anchors)
        }
        return len(used)

    def _run_case(self, case: DeepSummaryEvalCase) -> DeepSummaryCaseResult:
        try:
            chunks = self._make_chunks(case)
            thresholds = self._merge_thresholds(case)
            signals = detect_coverage_signals(chunks)
            profile = resolve_coverage_profile(
                case.doc_name,
                signals,
                configured_profile=getattr(config, "summary_coverage_profile", "auto"),
            )
            coverage = score_coverage(
                case.summary_text,
                signals,
                coverage_profile=profile,
            )
            topic_info = extract_document_topics(chunks, major_topic_min_hits=2)
            outline_cov = score_topic_outline_coverage(case.summary_text, topic_info)
            outline_score = float(outline_cov.get("overall_score", 1.0))
            formula_mode = str(
                thresholds.get("formula_mode")
                or getattr(config, "summary_formula_mode", "conservative")
            ).strip().lower()

            claim_risk = classify_claim_risks(case.summary_text, chunks)
            claim_risk = check_formula_mode(claim_risk, chunks, formula_mode)
            inference = compute_inference_density(claim_risk)
            unsupported_high_risk_count = int(
                claim_risk.get("unsupported_high_risk_count", 0)
            )
            formula_claims_downgraded = int(
                claim_risk.get("formula_claims_downgraded_to_concept", 0)
            )
            inference_density = float(inference.get("inference_density", 0.0))

            structure = validate_summary_structure(
                case.summary_text,
                min_section_chars=int(thresholds.get("structure_min_chars", 40)),
            )
            _, grounding = validate_summary_grounding(
                case.summary_text,
                chunks,
                threshold=float(getattr(config, "summary_grounding_threshold", 0.20)),
                llm=None,
            )
            cited_blocks = int(grounding.get("blocks_with_citations", 0))
            weak_blocks = int(grounding.get("weakly_grounded", 0))
            weak_ratio = (weak_blocks / cited_blocks) if cited_blocks > 0 else 0.0

            unique_sources = self._count_unique_sources(case.summary_text, len(chunks))
            failures: list[str] = []

            if bool(thresholds.get("require_structure_valid", True)) and not bool(structure.get("valid")):
                failures.append("structure_invalid")
            if float(coverage.get("overall_coverage_score", 1.0)) < float(thresholds.get("min_coverage_score", 0.50)):
                failures.append("coverage_below_min")
            if weak_ratio > float(thresholds.get("max_weak_grounding_ratio", 0.50)):
                failures.append("weak_grounding_ratio_above_max")
            if unique_sources < int(thresholds.get("min_unique_sources", 2)):
                failures.append("unique_sources_below_min")
            min_outline = thresholds.get("min_outline_coverage_score")
            if min_outline is not None and outline_score < float(min_outline):
                failures.append("outline_coverage_below_min")
            max_outline = thresholds.get("max_outline_coverage_score")
            if max_outline is not None and outline_score > float(max_outline):
                failures.append("outline_coverage_above_max")
            min_unsupported = thresholds.get("min_unsupported_high_risk_count")
            if (
                min_unsupported is not None
                and unsupported_high_risk_count < int(min_unsupported)
            ):
                failures.append("unsupported_high_risk_below_min")
            max_unsupported = thresholds.get("max_unsupported_high_risk_count")
            if (
                max_unsupported is not None
                and unsupported_high_risk_count > int(max_unsupported)
            ):
                failures.append("unsupported_high_risk_above_max")
            min_formula_down = thresholds.get("min_formula_claims_downgraded")
            if (
                min_formula_down is not None
                and formula_claims_downgraded < int(min_formula_down)
            ):
                failures.append("formula_claims_downgraded_below_min")
            max_formula_down = thresholds.get("max_formula_claims_downgraded")
            if (
                max_formula_down is not None
                and formula_claims_downgraded > int(max_formula_down)
            ):
                failures.append("formula_claims_downgraded_above_max")
            min_inference = thresholds.get("min_inference_density")
            if min_inference is not None and inference_density < float(min_inference):
                failures.append("inference_density_below_min")
            max_inference = thresholds.get("max_inference_density")
            if max_inference is not None and inference_density > float(max_inference):
                failures.append("inference_density_above_max")

            return DeepSummaryCaseResult(
                case_id=case.id,
                doc_name=case.doc_name,
                passed=not failures,
                structure_valid=bool(structure.get("valid", False)),
                coverage_score=float(coverage.get("overall_coverage_score", 1.0)),
                outline_coverage_score=round(outline_score, 4),
                weak_grounding_ratio=round(weak_ratio, 4),
                unique_sources_used=unique_sources,
                unsupported_high_risk_count=unsupported_high_risk_count,
                formula_claims_downgraded_to_concept=formula_claims_downgraded,
                inference_density=round(inference_density, 4),
                profile_name=str(profile.get("name", "balanced")),
                thresholds=thresholds,
                failure_reasons=failures,
            )
        except Exception as exc:
            thresholds = self._merge_thresholds(case)
            return DeepSummaryCaseResult(
                case_id=case.id,
                doc_name=case.doc_name,
                passed=False,
                structure_valid=False,
                coverage_score=0.0,
                outline_coverage_score=0.0,
                weak_grounding_ratio=1.0,
                unique_sources_used=0,
                unsupported_high_risk_count=0,
                formula_claims_downgraded_to_concept=0,
                inference_density=0.0,
                profile_name="error",
                thresholds=thresholds,
                failure_reasons=["runner_exception"],
                error=str(exc),
            )

    def run(self) -> DeepSummaryEvalReport:
        results = [self._run_case(case) for case in self.suite.cases]
        total = len(results)
        failed = sum(1 for r in results if not r.passed)
        passed = total - failed
        summary = {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": failed,
            "pass_rate": round((passed / total), 3) if total else 1.0,
            "avg_coverage_score": round(
                sum(r.coverage_score for r in results) / total, 3
            ) if total else 1.0,
            "avg_outline_coverage_score": round(
                sum(r.outline_coverage_score for r in results) / total, 3
            ) if total else 1.0,
            "avg_weak_grounding_ratio": round(
                sum(r.weak_grounding_ratio for r in results) / total, 3
            ) if total else 0.0,
            "avg_inference_density": round(
                sum(r.inference_density for r in results) / total, 3
            ) if total else 0.0,
        }
        return DeepSummaryEvalReport(
            suite_name=self.suite.suite_name,
            run_at=datetime.now(timezone.utc).isoformat(),
            settings={"suite_path": str(self.suite_path)},
            summary=summary,
            cases=results,
        )

    def save(self, report: DeepSummaryEvalReport, output_path: str | Path) -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(asdict(report), fh, ensure_ascii=False, indent=2)
        return out
