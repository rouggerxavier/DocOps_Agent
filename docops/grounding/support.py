"""Claim-to-evidence support checker."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Literal

from langchain_core.documents import Document

from docops.config import config
from docops.logging import get_logger

logger = get_logger("docops.grounding.support")

SupportLabel = Literal["SUPPORTED", "NOT_SUPPORTED", "UNCLEAR"]

_STOPWORDS = frozenset(
    {
        "a",
        "o",
        "e",
        "de",
        "do",
        "da",
        "em",
        "para",
        "com",
        "que",
        "se",
        "por",
        "um",
        "uma",
        "os",
        "as",
        "dos",
        "das",
        "no",
        "na",
        "the",
        "is",
        "are",
        "was",
        "were",
        "and",
        "or",
        "in",
        "on",
        "of",
        "to",
        "an",
        "that",
        "this",
        "it",
        "at",
        "be",
        "has",
        "have",
        "nao",
    }
)

_UNIT_RE = re.compile(
    r"\b\d+(?:[\.,]\d+)?\s*(?:%|ms|s|min|h|kg|g|mg|km|m|cm|mm|gb|mb|kb|r\$|usd|eur)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{4})\b"
)


@dataclass
class SupportResult:
    label: SupportLabel
    score: float
    rationale: str


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"\b[\w\-]{3,}\b", text.lower()))
    return tokens - _STOPWORDS


def _extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", text))


def _extract_dates(text: str) -> set[str]:
    return set(_DATE_RE.findall(text))


def _extract_units(text: str) -> set[str]:
    return set(_UNIT_RE.findall(text))


def _extract_entities(text: str) -> set[str]:
    # lightweight proxy for named entities: capitalized words/acronyms
    return set(re.findall(r"\b(?:[A-Z][a-z]{2,}|[A-Z]{2,})\b", text))


def _score_match(claim_items: set[str], evidence_items: set[str], default: float = 1.0) -> float:
    if not claim_items:
        return default
    matched = claim_items & evidence_items
    return len(matched) / max(len(claim_items), 1)


def _heuristic_support(claim: str, evidence: str) -> SupportResult:
    claim_tokens = _tokenize(claim)
    evidence_tokens = _tokenize(evidence)
    if not claim_tokens:
        return SupportResult("UNCLEAR", 0.5, "Claim has no significant tokens.")

    overlap_score = _score_match(claim_tokens, evidence_tokens, default=0.0)
    num_score = _score_match(_extract_numbers(claim), _extract_numbers(evidence))
    date_score = _score_match(_extract_dates(claim), _extract_dates(evidence))
    entity_score = _score_match(_extract_entities(claim), _extract_entities(evidence))
    unit_score = _score_match(_extract_units(claim), _extract_units(evidence))

    score = round(
        (0.45 * overlap_score)
        + (0.25 * num_score)
        + (0.15 * date_score)
        + (0.10 * entity_score)
        + (0.05 * unit_score),
        4,
    )
    threshold = config.grounded_verifier_threshold

    if score >= threshold:
        label: SupportLabel = "SUPPORTED"
    elif score >= (threshold * 0.6):
        label = "UNCLEAR"
    else:
        label = "NOT_SUPPORTED"

    rationale = (
        f"overlap={overlap_score:.2f}, numbers={num_score:.2f}, dates={date_score:.2f}, "
        f"entities={entity_score:.2f}, units={unit_score:.2f}, score={score:.2f}"
    )
    return SupportResult(label=label, score=score, rationale=rationale)


_LLM_PROMPT = (
    "You are a strict grounding judge.\n"
    "Given CLAIM and EVIDENCE, decide if evidence supports claim.\n"
    "Return JSON only: "
    "{\"label\":\"SUPPORTED|NOT_SUPPORTED|UNCLEAR\",\"score\":0.0,\"rationale\":\"...\"}\n\n"
    "CLAIM: {claim}\n\nEVIDENCE: {evidence}"
)


def _llm_support(claim: str, evidence: str) -> SupportResult:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(
            model=config.gemini_model,
            google_api_key=config.gemini_api_key,
            temperature=0.0,
        )
        response = llm.invoke(
            [HumanMessage(content=_LLM_PROMPT.format(claim=claim, evidence=evidence[:1200]))]
        )
        raw = response.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return _heuristic_support(claim, evidence)
        parsed = json.loads(match.group(0))
        label = str(parsed.get("label", "UNCLEAR")).upper()
        if label not in {"SUPPORTED", "NOT_SUPPORTED", "UNCLEAR"}:
            label = "UNCLEAR"
        return SupportResult(
            label=label,  # type: ignore[arg-type]
            score=float(parsed.get("score", 0.5)),
            rationale=str(parsed.get("rationale", "")),
        )
    except Exception as exc:
        logger.warning(f"LLM support check failed ({exc}); using heuristic.")
        return _heuristic_support(claim, evidence)


def check_support(claim: str, evidence_text: str, mode: str | None = None) -> SupportResult:
    """Check support label/score for claim against one evidence text."""
    effective_mode = (mode or config.grounded_verifier_mode).lower()
    if effective_mode == "llm":
        return _llm_support(claim, evidence_text)
    if effective_mode == "hybrid":
        first = _heuristic_support(claim, evidence_text)
        if first.label == "UNCLEAR":
            return _llm_support(claim, evidence_text)
        return first
    return _heuristic_support(claim, evidence_text)


def compute_support_rate(
    claims: List[str],
    evidence_chunks: List[Document],
    mode: str | None = None,
) -> dict:
    """Compute support rate by taking best evidence score per claim."""
    if not claims:
        return {"support_rate": 1.0, "unsupported_claims": [], "results": []}

    per_claim_results = []
    unsupported: List[str] = []
    for claim in claims:
        best = SupportResult("NOT_SUPPORTED", 0.0, "No evidence chunk.")
        for chunk in evidence_chunks:
            ev_text = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
            result = check_support(claim, ev_text, mode=mode)
            if result.score > best.score:
                best = result
        per_claim_results.append(
            {
                "claim": claim,
                "label": best.label,
                "score": best.score,
                "rationale": best.rationale,
            }
        )
        if best.label != "SUPPORTED":
            unsupported.append(claim)

    supported_count = sum(1 for r in per_claim_results if r["label"] == "SUPPORTED")
    support_rate = round(supported_count / len(per_claim_results), 3)
    return {
        "support_rate": support_rate,
        "unsupported_claims": unsupported,
        "results": per_claim_results,
    }

