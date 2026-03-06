"""Eval harness runner for DocOps Agent."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List

from docops.config import config

logger = logging.getLogger("docops.eval.runner")

_ABSTAIN_RE = re.compile(
    r"(nao encontrei|não encontrei|nao ha informacao|não há informação|"
    r"nao consta|não consta|not found|no information|cannot find)",
    re.IGNORECASE,
)
_CITATION_RE = re.compile(r"\[Fonte\s*(\d+)\]", re.IGNORECASE)
_FACTUAL_RE = re.compile(
    r"\b\d{4}\b|\b\d+[\.,]\d+\b|\b\d+\s*%|\bsegundo\b|\bconforme\b|"
    r"\bde acordo com\b|\bbecause\b|\bdefine(-se)?\b|\bconsiste\b|\bcont[eé]m\b",
    re.IGNORECASE,
)


@dataclass
class EvalCase:
    id: str
    question: str
    expected: str | list[str] | None = None
    must_cite: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class EvalSuite:
    suite_name: str
    description: str = ""
    corpus: List[str] = field(default_factory=list)
    cases: List[EvalCase] = field(default_factory=list)


def load_suite(path: str | Path) -> EvalSuite:
    """Load eval suite YAML and return a parsed dataclass."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("pyyaml is required for eval suites: pip install pyyaml") from exc

    suite_path = Path(path)
    with suite_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    cases = []
    for item in raw.get("cases", []):
        cases.append(
            EvalCase(
                id=str(item["id"]),
                question=str(item["question"]),
                expected=item.get("expected"),
                must_cite=list(item.get("must_cite") or []),
                tags=list(item.get("tags") or []),
            )
        )

    return EvalSuite(
        suite_name=str(raw["suite_name"]),
        description=str(raw.get("description") or ""),
        corpus=list(raw.get("corpus") or []),
        cases=cases,
    )


def _split_sentences(text: str) -> List[str]:
    raw = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [s.strip() for s in raw if s.strip() and len(s.strip()) > 8]


def citation_coverage(answer: str) -> float:
    """Fraction of factual sentences that include at least one [Fonte N]."""
    sentences = _split_sentences(answer)
    factual = [s for s in sentences if _FACTUAL_RE.search(s)]
    if not factual:
        return 1.0
    cited = [s for s in factual if _CITATION_RE.search(s)]
    return round(len(cited) / len(factual), 3)


def _select_cited_chunks(answer: str, chunks: list) -> list:
    matches = [int(m) for m in _CITATION_RE.findall(answer)]
    if not matches:
        return chunks
    selected = []
    for idx in matches:
        if 1 <= idx <= len(chunks):
            selected.append(chunks[idx - 1])
    return selected or chunks


def citation_support_rate(answer: str, chunks: list) -> float:
    """Fraction of cited claims that are semantically supported."""
    try:
        from docops.grounding.claims import extract_cited_claims
        from docops.grounding.support import compute_support_rate

        cited = extract_cited_claims(answer)
        claims = [item["claim"] for item in cited]
        if not claims:
            return 1.0

        selected_chunks = _select_cited_chunks(answer, chunks)
        support = compute_support_rate(
            claims,
            selected_chunks,
            mode=config.grounded_verifier_mode,
        )
        return float(support.get("support_rate", 0.0))
    except Exception:
        return 0.0


def is_abstention(answer: str) -> bool:
    return bool(_ABSTAIN_RE.search(answer))


def retrieval_recall_proxy(question: str, chunks: list, answer: str = "") -> float:
    """Keyword recall over cited chunks (fallback: all chunks)."""
    keywords = set(re.findall(r"\b\w{4,}\b", question.lower()))
    if not keywords:
        return 1.0

    selected_chunks = _select_cited_chunks(answer, chunks)
    haystack = " ".join(
        c.page_content if hasattr(c, "page_content") else str(c) for c in selected_chunks
    ).lower()
    found = sum(1 for kw in keywords if kw in haystack)
    return round(found / len(keywords), 3)


def must_cite_pass(answer: str, must_cite: List[str], chunks: list | None = None) -> bool:
    """Check required patterns against answer and formatted source metadata."""
    if not must_cite:
        return True
    chunks = chunks or []
    source_blob_parts: list[str] = []
    for c in chunks:
        meta = c.metadata if hasattr(c, "metadata") else {}
        source_blob_parts.append(str(meta.get("file_name", "")))
        source_blob_parts.append(str(meta.get("page", "")))
        source_blob_parts.append(str(meta.get("section_path", "")))
    source_blob = " ".join(source_blob_parts)
    target = f"{answer}\n{source_blob}"
    return all(re.search(pattern, target, re.IGNORECASE) for pattern in must_cite)


def expected_match(answer: str, expected: str | list[str] | None) -> bool:
    """Simple expected-answer matcher (substring heuristic)."""
    if expected is None:
        return True
    if isinstance(expected, list):
        if not expected:
            return True
        return any(str(item).lower() in answer.lower() for item in expected)
    return str(expected).lower() in answer.lower()


AgentFn = Callable[[str], dict]


def _default_agent_fn(
    question: str,
    top_k: int = 6,
    retrieval: str = "mmr",
    rerank: bool = False,
    seed: int | None = None,
) -> dict:
    import os

    if retrieval:
        os.environ["RETRIEVAL_MODE"] = retrieval
    os.environ["RERANKER"] = "local" if rerank else "none"
    if seed is not None:
        os.environ["PYTHONHASHSEED"] = str(seed)

    from docops.graph.graph import run as graph_run

    state = graph_run(query=question, top_k=top_k)
    return {
        "answer": state.get("answer", ""),
        "retrieved_chunks": state.get("retrieved_chunks", []),
        "grounding": state.get("grounding") or state.get("grounding_info"),
    }


@dataclass
class CaseResult:
    case_id: str
    question: str
    tags: List[str]
    answer: str
    citation_coverage: float
    citation_support_rate: float
    is_abstention: bool
    expected_abstention: bool
    abstention_correct: bool
    retrieval_recall_proxy: float
    must_cite_pass: bool
    expected_match: bool
    strict_pass: bool
    error: str | None = None


@dataclass
class EvalReport:
    suite_name: str
    run_at: str
    settings: dict
    summary: dict
    cases: List[CaseResult]


class EvalRunner:
    """Run an eval suite against the DocOps pipeline and collect metrics."""

    def __init__(
        self,
        suite_path: str | Path,
        top_k: int = 6,
        retrieval: str = "mmr",
        rerank: bool = False,
        seed: int | None = None,
        strict: bool = False,
        max_cases: int | None = None,
        agent_fn: AgentFn | None = None,
    ) -> None:
        self.suite = load_suite(suite_path)
        self.top_k = top_k
        self.retrieval = retrieval
        self.rerank = rerank
        self.seed = seed
        self.strict = strict
        self.max_cases = max_cases
        self._agent_fn = agent_fn or (
            lambda q: _default_agent_fn(
                q,
                top_k=self.top_k,
                retrieval=self.retrieval,
                rerank=self.rerank,
                seed=self.seed,
            )
        )

    def run(self) -> EvalReport:
        cases = self.suite.cases[: self.max_cases] if self.max_cases else self.suite.cases
        results = [self._run_case(case) for case in cases]
        for item in results:
            self._log_case(item)

        summary = self._summarise(results)
        return EvalReport(
            suite_name=self.suite.suite_name,
            run_at=datetime.now(timezone.utc).isoformat(),
            settings={
                "top_k": self.top_k,
                "retrieval": self.retrieval,
                "rerank": self.rerank,
                "seed": self.seed,
                "strict": self.strict,
            },
            summary=summary,
            cases=results,
        )

    def _run_case(self, case: EvalCase) -> CaseResult:
        try:
            result = self._agent_fn(case.question)
            answer = str(result.get("answer", ""))
            chunks = result.get("retrieved_chunks", []) or []

            cov = citation_coverage(answer)
            csr = citation_support_rate(answer, chunks)
            abst = is_abstention(answer)
            expected_abst = (case.expected == "" and not case.must_cite)
            recall = retrieval_recall_proxy(case.question, chunks, answer=answer)
            mc_pass = must_cite_pass(answer, case.must_cite, chunks=chunks)
            exp_match = expected_match(answer, case.expected)

            strict_pass = True
            if self.strict and ("factual" in case.tags or "numbers" in case.tags):
                strict_pass = cov >= 1.0

            return CaseResult(
                case_id=case.id,
                question=case.question,
                tags=case.tags,
                answer=answer,
                citation_coverage=cov,
                citation_support_rate=csr,
                is_abstention=abst,
                expected_abstention=expected_abst,
                abstention_correct=(abst == expected_abst),
                retrieval_recall_proxy=recall,
                must_cite_pass=mc_pass,
                expected_match=exp_match,
                strict_pass=strict_pass,
            )
        except Exception as exc:
            logger.error(f"Case '{case.id}' failed: {exc}", exc_info=True)
            return CaseResult(
                case_id=case.id,
                question=case.question,
                tags=case.tags,
                answer="",
                citation_coverage=0.0,
                citation_support_rate=0.0,
                is_abstention=False,
                expected_abstention=(case.expected == "" and not case.must_cite),
                abstention_correct=False,
                retrieval_recall_proxy=0.0,
                must_cite_pass=False,
                expected_match=False,
                strict_pass=False,
                error=str(exc),
            )

    def _log_case(self, result: CaseResult) -> None:
        status = "OK" if not result.error else "ERROR"
        logger.info(
            f"[{status}] {result.case_id}: cov={result.citation_coverage:.2f}, "
            f"csr={result.citation_support_rate:.2f}, recall={result.retrieval_recall_proxy:.2f}, "
            f"abstain={result.is_abstention}/{result.expected_abstention}, strict={result.strict_pass}"
        )

    def _summarise(self, results: List[CaseResult]) -> dict:
        if not results:
            return {}
        ok = [r for r in results if not r.error]
        n = len(ok) or 1
        return {
            "total_cases": len(results),
            "errors": len(results) - len(ok),
            "avg_citation_coverage": round(sum(r.citation_coverage for r in ok) / n, 3),
            "avg_citation_support_rate": round(sum(r.citation_support_rate for r in ok) / n, 3),
            "abstention_accuracy": round(sum(1 for r in ok if r.abstention_correct) / n, 3),
            "avg_retrieval_recall_proxy": round(sum(r.retrieval_recall_proxy for r in ok) / n, 3),
            "must_cite_pass_rate": round(sum(1 for r in ok if r.must_cite_pass) / n, 3),
            "expected_match_rate": round(sum(1 for r in ok if r.expected_match) / n, 3),
            "strict_pass_rate": round(sum(1 for r in ok if r.strict_pass) / n, 3),
        }

    def save(self, report: EvalReport, output_path: str | Path) -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(asdict(report), fh, ensure_ascii=False, indent=2)
        logger.info(f"Eval report saved to {out}")
        return out

