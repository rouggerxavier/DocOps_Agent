"""Extract factual claims from answer text."""

from __future__ import annotations

import json
import re
from typing import List

from docops.config import config
from docops.llm.content import response_text
from docops.llm.router import build_chat_model
from docops.logging import get_logger

logger = get_logger("docops.grounding.claims")

_FACTUAL_MARKERS = [
    r"\b\d{4}\b",
    r"\b\d+[\.,]\d+\b",
    r"\b\d+\s*%",
    r"\bsegundo\b",
    r"\bconforme\b",
    r"\bde acordo com\b",
    r"\bbecause\b",
    r"\bportanto\b",
    r"\bdefine(-se)?\b",
    r"\bconsiste\b",
    r"\bcont[eé]m\b",
    r"\bapresenta\b",
    r"\bfoi criado\b",
    r"\blan[cç]ado em\b",
    r"\bpublicado em\b",
    r"\baccording to\b",
    r"\bdefined as\b",
]

_FACTUAL_RE = re.compile("|".join(_FACTUAL_MARKERS), re.IGNORECASE)
_CITATION_RE = re.compile(r"\[Fonte\s*\d+\]", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")

_CLAIMS_LLM_PROMPT = """\
Você é um extrator de afirmações factuais. Analise o texto abaixo e extraia todas as frases que contêm afirmações verificáveis — fatos, números, datas, definições, relações causais, resultados, atribuições de autoria.

REGRAS:
- Inclua afirmações mesmo que não sigam padrões linguísticos específicos.
- Não limite a lista por forma gramatical — use o significado, não palavras-chave.
- Se uma frase contiver múltiplas afirmações, mantenha-a inteira.
- Se houver incerteza se é factual, prefira incluir.
- Se o texto não tiver afirmações verificáveis, retorne lista vazia.
- Responda APENAS com JSON válido, sem texto antes ou depois.

FORMATO: {{"claims": ["frase1", "frase2", ...]}}

TEXTO:
{text}"""


def extract_sentences(text: str) -> List[str]:
    """Split text into candidate sentences using lightweight heuristics."""
    raw = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in raw if s.strip() and len(s.strip()) > 10]


def _heuristic_claims(text: str, include_cited: bool = False) -> List[str]:
    claims = []
    for sentence in extract_sentences(text):
        if not _FACTUAL_RE.search(sentence):
            continue
        if not include_cited and _CITATION_RE.search(sentence):
            continue
        claims.append(sentence)
    return claims


def _llm_claims(text: str) -> List[str]:
    """Optional LLM extraction pass used in llm/hybrid claim modes."""
    try:
        from langchain_core.messages import HumanMessage

        llm = build_chat_model(route="cheap", temperature=0.0)
        response = llm.invoke(
            [HumanMessage(content=_CLAIMS_LLM_PROMPT.format(text=text[:4000]))]
        )
        raw = response_text(response)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return []
        parsed = json.loads(match.group(0))
        claims = parsed.get("claims", [])
        if not isinstance(claims, list):
            return []
        return [str(c).strip() for c in claims if str(c).strip()]
    except Exception as exc:
        logger.warning(f"LLM claim extraction failed: {exc}")
        return []


def _dedupe(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        normalized = re.sub(r"\s+", " ", item.strip().lower())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(item.strip())
    return out


def extract_claims(
    text: str,
    include_cited: bool = False,
    mode: str | None = None,
) -> List[str]:
    """Extract factual claims with heuristic/llm/hybrid configurable mode."""
    effective_mode = (mode or config.grounded_claims_mode).lower()
    heur = _heuristic_claims(text, include_cited=include_cited)

    if effective_mode == "heuristic":
        return _dedupe(heur)

    llm_claims = _llm_claims(text)
    if effective_mode == "llm":
        if include_cited:
            return _dedupe(llm_claims)
        return _dedupe([c for c in llm_claims if not _CITATION_RE.search(c)])

    merged = heur + llm_claims
    if not include_cited:
        merged = [c for c in merged if not _CITATION_RE.search(c)]
    return _dedupe(merged)


def extract_cited_claims(text: str) -> List[dict]:
    """Return cited factual claims as {'claim': str, 'citations': list[str]}."""
    cited = []
    for sentence in extract_sentences(text):
        citations = _CITATION_RE.findall(sentence)
        if citations:
            cited.append({"claim": sentence, "citations": citations})
    return cited
